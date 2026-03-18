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
from agents.core.guards import MAX_TOOL_CALLS_PER_NODE, MAX_TOTAL_TOOL_CALLS, pre_node_guard
from agents.core.state import FeedbackState, initial_feedback_state
from agents.core.workflow_helpers import (
    accumulate_usage,
    apply_file_changes,
    update_node_tool_calls,
)
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
    guard = pre_node_guard(state, "gather_feedback_node")
    if not guard.allowed:
        return {"status": "failed", "error_log": state["error_log"] + [guard.reason]}

    comments = get_pr_comments(state["pr_number"])
    comment_dicts = [c.model_dump() for c in comments]
    return {
        "feedback_comments": comment_dicts,
        "status": "implementing",
        "total_tool_calls": state["total_tool_calls"] + 1,
        "node_tool_calls": update_node_tool_calls(state, "gather_feedback_node", 1),
    }


async def implement_feedback_node(state: FeedbackState) -> dict[str, Any]:
    """Run the implementer with feedback-aware prompt."""
    guard = pre_node_guard(state, "implement_feedback_node")
    if not guard.allowed:
        return {"status": "failed", "error_log": state["error_log"] + [guard.reason]}

    iteration = state["iteration_count"] + 1
    feedback_task = _format_feedback_prompt(state)

    planner_context = build_context(feedback_task, worker_role="planner")
    plan, plan_usage, plan_tool_calls = await run_planner(feedback_task, planner_context)

    impl_context = build_context(feedback_task, worker_role="implementer")
    impl, usage, tool_calls = await run_implementer(
        task=feedback_task,
        plan=plan,
        context=impl_context,
        previous_validation=state["validation"],
        iteration=iteration,
    )

    apply_file_changes(impl.files_changed)

    combined_usage = TokenUsage(
        tokens_in=plan_usage.tokens_in + usage.tokens_in,
        tokens_out=plan_usage.tokens_out + usage.tokens_out,
    )

    node_calls = plan_tool_calls + tool_calls + 2
    return {
        "files_changed": impl.files_changed,
        "iteration_count": iteration,
        **accumulate_usage(state, combined_usage, "implement_feedback_node", node_calls),
        "total_tool_calls": state["total_tool_calls"] + node_calls,
        "status": "validating",
    }


async def validate_feedback_node(state: FeedbackState) -> dict[str, Any]:
    """Run tests and lint on changes."""
    guard = pre_node_guard(state, "validate_feedback_node")
    if not guard.allowed:
        return {"status": "failed", "error_log": state["error_log"] + [guard.reason]}

    validation = await run_validator(iteration=state["iteration_count"])
    node_calls = 2  # run_tests + run_lint
    return {
        "validation": validation,
        "total_tool_calls": state["total_tool_calls"] + node_calls,
        "node_tool_calls": update_node_tool_calls(state, "validate_feedback_node", node_calls),
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
    guard = pre_node_guard(state, "commit_push_node")
    if not guard.allowed:
        return {"status": "failed", "error_log": state["error_log"] + [guard.reason]}

    changed_paths = [f.path for f in state["files_changed"]]
    if not changed_paths:
        return {
            "status": "failed",
            "error_log": state["error_log"] + ["No files changed to commit."],
            "total_tool_calls": state["total_tool_calls"],
            "node_tool_calls": update_node_tool_calls(state, "commit_push_node", 0),
        }

    commit_result = commit(
        message=f"fix: address reviewer feedback on PR #{state['pr_number']}",
        files=changed_paths,
    )
    if not commit_result.success:
        return {
            "status": "failed",
            "error_log": state["error_log"] + [f"Commit failed: {commit_result.error}"],
            "total_tool_calls": state["total_tool_calls"] + 1,
            "node_tool_calls": update_node_tool_calls(state, "commit_push_node", 1),
        }

    push_result = push_to_remote(state["pr_branch"])
    if not push_result.success:
        return {
            "status": "failed",
            "error_log": state["error_log"] + [f"Push failed: {push_result.error}"],
            "total_tool_calls": state["total_tool_calls"] + 2,
            "node_tool_calls": update_node_tool_calls(state, "commit_push_node", 2),
        }

    node_calls = 2
    return {
        "status": "replying",
        "total_tool_calls": state["total_tool_calls"] + node_calls,
        "node_tool_calls": update_node_tool_calls(state, "commit_push_node", node_calls),
    }


async def reply_node(state: FeedbackState) -> dict[str, Any]:
    """Reply to each review comment explaining what was changed."""
    guard = pre_node_guard(state, "reply_node")
    if not guard.allowed:
        return {"status": "failed", "error_log": state["error_log"] + [guard.reason]}

    changed_summary = ", ".join(f"`{f.path}`" for f in state["files_changed"])
    reply_body = (
        f"Addressed in the latest commit. Files changed: {changed_summary}.\n\n"
        f"_Automated feedback response by Ouroboros agent._"
    )

    existing_node_calls = state.get("node_tool_calls", {}).get("reply_node", 0)
    attempts = 0
    succeeded = 0
    hit_limit = False
    for comment in state["feedback_comments"]:
        comment_id = comment.get("id")
        if not comment_id:
            continue
        attempts += 1
        if reply_to_pr_comment(int(comment_id), reply_body):
            succeeded += 1
        current_total = state["total_tool_calls"] + attempts
        if existing_node_calls + attempts > MAX_TOOL_CALLS_PER_NODE:
            logfire.warning(
                "reply_node hit per-node tool call limit mid-loop",
                attempts=attempts,
                succeeded=succeeded,
                total_comments=len(state["feedback_comments"]),
                limit=MAX_TOOL_CALLS_PER_NODE,
            )
            hit_limit = True
            break
        if current_total >= MAX_TOTAL_TOOL_CALLS:
            logfire.warning(
                "reply_node hit global tool call budget mid-loop",
                attempts=attempts,
                succeeded=succeeded,
                total_calls=current_total,
                limit=MAX_TOTAL_TOOL_CALLS,
            )
            hit_limit = True
            break

    logfire.info(
        "feedback_replies_sent",
        attempts=attempts,
        succeeded=succeeded,
        total=len(state["feedback_comments"]),
    )
    if hit_limit:
        return {
            "status": "escalated",
            "error_log": state["error_log"]
            + [
                f"reply_node answered {succeeded}/{len(state['feedback_comments'])} "
                f"comments ({attempts} attempts) before hitting per-node tool call "
                f"limit ({MAX_TOOL_CALLS_PER_NODE})."
            ],
            "total_tool_calls": state["total_tool_calls"] + attempts,
            "node_tool_calls": update_node_tool_calls(state, "reply_node", attempts),
        }
    return {
        "status": "done",
        "total_tool_calls": state["total_tool_calls"] + attempts,
        "node_tool_calls": update_node_tool_calls(state, "reply_node", attempts),
    }


def _feedback_status_gate(state: FeedbackState, next_node: str) -> str:
    """Route to END on failure/escalation, otherwise continue."""
    if state.get("status") in ("failed", "escalated"):
        return END
    return next_node


def route_after_gather(state: FeedbackState) -> str:
    return _feedback_status_gate(state, "implement_feedback_node")


def route_after_implement_feedback(state: FeedbackState) -> str:
    return _feedback_status_gate(state, "validate_feedback_node")


def route_after_commit_push(state: FeedbackState) -> str:
    return _feedback_status_gate(state, "reply_node")


def build_feedback_graph() -> StateGraph:
    graph = StateGraph(FeedbackState)

    graph.add_node("gather_feedback_node", gather_feedback_node)
    graph.add_node("implement_feedback_node", implement_feedback_node)
    graph.add_node("validate_feedback_node", validate_feedback_node)
    graph.add_node("commit_push_node", commit_push_node)
    graph.add_node("reply_node", reply_node)

    graph.set_entry_point("gather_feedback_node")
    graph.add_conditional_edges("gather_feedback_node", route_after_gather)
    graph.add_conditional_edges("implement_feedback_node", route_after_implement_feedback)
    graph.add_conditional_edges("validate_feedback_node", route_after_validate)
    graph.add_conditional_edges("commit_push_node", route_after_commit_push)
    graph.add_edge("reply_node", END)

    return graph


async def run_feedback_loop(
    pr_number: int,
    pr_branch: str,
    original_task: str,
    feedback_comments: list[dict[str, object]],
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
