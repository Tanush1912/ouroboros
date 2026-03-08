"""Feedback Loop — respond to human PR review comments.

State machine:
  start → gather_feedback_node → implement_node → validate_node
         → [retry] → implement_node (max 5)
         → [proceed] → commit_push_node → reply_node → done
         → [escalate] → failed
"""

import time
from typing import Any

import logfire
from langgraph.graph import END, StateGraph

from agents.core.context_builder import build_context
from agents.core.state import FeedbackState, initial_feedback_state
from agents.models.cost import TokenUsage
from agents.tools.git import (
    commit,
    get_pr_comments,
    push_to_remote,
    reply_to_pr_comment,
)
from agents.workers.implementer import run_implementer
from agents.workers.planner import run_planner
from agents.workers.validator import run_validator

MAX_FEEDBACK_IMPLEMENT_ITERATIONS = 5
MAX_COST_USD = 2.00


def _accumulate_usage(state: FeedbackState, usage: TokenUsage, node_name: str) -> dict:
    """Return state updates for token/cost accumulation."""
    prev = state["node_token_usage"].get(node_name, {"tokens_in": 0, "tokens_out": 0})
    updated = dict(state["node_token_usage"])
    updated[node_name] = {
        "tokens_in": prev["tokens_in"] + usage.tokens_in,
        "tokens_out": prev["tokens_out"] + usage.tokens_out,
    }
    return {
        "total_tokens_in": state["total_tokens_in"] + usage.tokens_in,
        "total_tokens_out": state["total_tokens_out"] + usage.tokens_out,
        "estimated_cost_usd": state["estimated_cost_usd"] + usage.cost_usd(),
        "node_token_usage": updated,
    }


def _check_feedback_guard(state: FeedbackState) -> str | None:
    """Return an error reason if a guard is violated, else None."""
    if state["iteration_count"] >= MAX_FEEDBACK_IMPLEMENT_ITERATIONS:
        return f"Max implement iterations ({MAX_FEEDBACK_IMPLEMENT_ITERATIONS}) reached."
    if state["estimated_cost_usd"] >= state["cost_budget_usd"]:
        return f"Cost budget ${state['cost_budget_usd']:.2f} exceeded."
    return None


def _format_feedback_prompt(state: FeedbackState) -> str:
    """Build a prompt combining original task + PR diff + reviewer feedback."""
    parts = [f"## Original Task\n{state['original_task']}"]

    parts.append("## Reviewer Feedback — Address All Comments Below")
    for comment in state["feedback_comments"]:
        path = comment.get("path", "general")
        line = comment.get("line", "")
        body = comment.get("body", "")
        author = comment.get("author", "reviewer")
        loc = f"{path}:{line}" if line else str(path)
        parts.append(f"- **@{author}** on `{loc}`:\n  > {body}")

    if state["validation"] and not state["validation"].overall_pass:
        parts.append("## Previous Validation Failures")
        for f in state["validation"].tests.failures:
            parts.append(f"- Test: {f}")
        for v in state["validation"].lint.violations:
            parts.append(f"- Lint: {v}")

    return "\n\n".join(parts)


async def gather_feedback_node(state: FeedbackState) -> dict[str, Any]:
    """Fetch current PR comments and diff. Build feedback context."""
    comments = await get_pr_comments.fn(state["pr_number"])
    comment_dicts = [c.model_dump() for c in comments]
    return {
        "feedback_comments": comment_dicts,
        "status": "implementing",
        "total_tool_calls": state["total_tool_calls"] + 1,
    }


async def implement_feedback_node(state: FeedbackState) -> dict[str, Any]:
    """Run the implementer with feedback-aware prompt."""
    guard_reason = _check_feedback_guard(state)
    if guard_reason:
        return {"status": "failed", "error_log": state["error_log"] + [guard_reason]}

    iteration = state["iteration_count"] + 1
    feedback_task = _format_feedback_prompt(state)
    context = build_context(feedback_task)

    plan, plan_usage, plan_tool_calls = await run_planner(feedback_task, context)
    impl, usage, tool_calls = await run_implementer(
        task=feedback_task,
        plan=plan,
        context=context,
        previous_validation=state["validation"],
        iteration=iteration,
    )

    from agents.core.paths import repo_root as _repo_root

    root = _repo_root()
    for change in impl.files_changed:
        target = root / change.path
        if change.operation == "delete":
            target.unlink(missing_ok=True)
        elif change.content is not None:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(change.content, encoding="utf-8")

    combined_usage = TokenUsage(
        tokens_in=plan_usage.tokens_in + usage.tokens_in,
        tokens_out=plan_usage.tokens_out + usage.tokens_out,
    )

    return {
        "files_changed": impl.files_changed,
        "iteration_count": iteration,
        **_accumulate_usage(state, combined_usage, "implement_feedback_node"),
        "total_tool_calls": state["total_tool_calls"] + plan_tool_calls + tool_calls + 2,
        "status": "validating",
    }


async def validate_feedback_node(state: FeedbackState) -> dict[str, Any]:
    """Run tests and lint on changes."""
    guard_reason = _check_feedback_guard(state)
    if guard_reason:
        return {"status": "failed", "error_log": state["error_log"] + [guard_reason]}

    validation = await run_validator(iteration=state["iteration_count"])
    return {
        "validation": validation,
        "total_tool_calls": state["total_tool_calls"] + 2,
        "status": "validating",
    }


def route_after_validate(state: FeedbackState) -> str:
    if state["status"] == "failed":
        return END
    validation = state["validation"]
    if validation is None:
        return END
    if validation.next_action == "proceed":
        return "commit_push_node"
    if validation.next_action == "retry":
        return "implement_feedback_node"
    return END  # escalate


async def commit_push_node(state: FeedbackState) -> dict[str, Any]:
    """Commit changed files and push to the PR branch."""
    changed_paths = [f.path for f in state["files_changed"]]
    if not changed_paths:
        return {
            "status": "failed",
            "error_log": state["error_log"] + ["No files changed to commit."],
        }

    commit_result = await commit.fn(
        message=f"fix: address reviewer feedback on PR #{state['pr_number']}",
        files=changed_paths,
    )
    if not commit_result.success:
        return {
            "status": "failed",
            "error_log": state["error_log"] + [f"Commit failed: {commit_result.error}"],
        }

    push_result = push_to_remote(state["pr_branch"])
    if not push_result.success:
        return {
            "status": "failed",
            "error_log": state["error_log"] + [f"Push failed: {push_result.error}"],
        }

    return {
        "status": "replying",
        "total_tool_calls": state["total_tool_calls"] + 2,
    }


async def reply_node(state: FeedbackState) -> dict[str, Any]:
    """Reply to each review comment explaining what was changed."""
    changed_summary = ", ".join(f"`{f.path}`" for f in state["files_changed"])
    reply_body = (
        f"Addressed in the latest commit. Files changed: {changed_summary}.\n\n"
        f"_Automated feedback response by Ouroboros agent._"
    )

    replied = 0
    for comment in state["feedback_comments"]:
        comment_id = comment.get("id")
        if comment_id and reply_to_pr_comment(int(comment_id), reply_body):
            replied += 1

    logfire.info("feedback_replies_sent", replied=replied, total=len(state["feedback_comments"]))
    return {
        "status": "done",
        "total_tool_calls": state["total_tool_calls"] + replied,
    }


def build_feedback_graph() -> StateGraph:
    graph = StateGraph(FeedbackState)

    graph.add_node("gather_feedback_node", gather_feedback_node)
    graph.add_node("implement_feedback_node", implement_feedback_node)
    graph.add_node("validate_feedback_node", validate_feedback_node)
    graph.add_node("commit_push_node", commit_push_node)
    graph.add_node("reply_node", reply_node)

    graph.set_entry_point("gather_feedback_node")
    graph.add_edge("gather_feedback_node", "implement_feedback_node")
    graph.add_edge("implement_feedback_node", "validate_feedback_node")
    graph.add_conditional_edges("validate_feedback_node", route_after_validate)
    graph.add_edge("commit_push_node", "reply_node")
    graph.add_edge("reply_node", END)

    return graph


async def run_feedback_loop(
    pr_number: int,
    pr_branch: str,
    original_task: str,
    feedback_comments: list[dict],
) -> FeedbackState:
    """Entry point: run the feedback loop for a PR. Returns final state."""
    start_time = time.monotonic()

    with logfire.span("feedback_loop", pr_number=pr_number):
        graph = build_feedback_graph()
        app = graph.compile()

        state = initial_feedback_state(
            pr_number=pr_number,
            pr_branch=pr_branch,
            original_task=original_task,
            feedback_comments=feedback_comments,
        )
        final_state = await app.ainvoke(state)

        duration = time.monotonic() - start_time
        logfire.info(
            "feedback_loop_complete",
            pr_number=pr_number,
            status=final_state["status"],
            iterations=final_state["iteration_count"],
            duration_seconds=duration,
            cost_usd=final_state["estimated_cost_usd"],
        )

    return final_state
