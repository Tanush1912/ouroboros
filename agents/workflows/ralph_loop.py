"""Ralph Loop — main PR lifecycle LangGraph workflow.

State machine:
  start → plan_node → implement_node → validate_node
         → [retry] → implement_node (max 5)
         → [escalate] → human_checkpoint
         → [proceed] → open_pr_node → review_loop_node
         → [not approved] → implement_node (address feedback)
         → [approved] → merge_node → done
"""

import time
from typing import Any

import logfire
from langgraph.graph import END, StateGraph

from agents.core.context_builder import build_context
from agents.core.guards import MAX_IMPLEMENT_ITERATIONS, pre_node_guard
from agents.core.state import RalphState, initial_state
from agents.models.cost import CostSummary, RunMetrics
from agents.tools.git import commit, merge_pr, open_pr
from agents.workers.implementer import run_implementer
from agents.workers.planner import run_planner
from agents.workers.reviewer import run_reviewer
from agents.workers.validator import run_validator


async def plan_node(state: RalphState) -> dict[str, Any]:
    guard = pre_node_guard(state, "plan_node")
    if not guard.allowed:
        return {"status": "escalated", "error_log": state["error_log"] + [guard.reason]}

    context = build_context(state["task"])
    plan = await run_planner(state["task"], context)
    return {"plan": plan, "status": "implementing"}


async def implement_node(state: RalphState) -> dict[str, Any]:
    guard = pre_node_guard(state, "implement_node")
    if not guard.allowed:
        return {
            "status": "escalated" if guard.action == "escalate" else "failed",
            "error_log": state["error_log"] + [guard.reason],
        }

    iteration = state["iteration_count"] + 1
    context = build_context(state["task"])
    impl = await run_implementer(
        task=state["task"],
        plan=state["plan"],
        context=context,
        previous_validation=state["validation"],
        iteration=iteration,
    )

    import aiofiles
    from pathlib import Path
    import subprocess

    repo_root = Path(subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True, text=True
    ).stdout.strip())

    for change in impl.files_changed:
        target = repo_root / change.path
        if change.operation == "delete":
            target.unlink(missing_ok=True)
        elif change.content is not None:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(change.content, encoding="utf-8")

    return {
        "files_changed": impl.files_changed,
        "iteration_count": iteration,
        "status": "validating",
    }


async def validate_node(state: RalphState) -> dict[str, Any]:
    guard = pre_node_guard(state, "validate_node")
    if not guard.allowed:
        return {"status": "escalated", "error_log": state["error_log"] + [guard.reason]}

    from agents.models.implementer import ImplementOutput
    fake_impl = ImplementOutput(
        files_changed=state["files_changed"],
        commit_message="",
        implementation_notes="",
        test_commands=[],
    )
    validation = await run_validator(fake_impl, iteration=state["iteration_count"])
    return {"validation": validation, "status": "validating"}


def route_after_validate(state: RalphState) -> str:
    if state["status"] == "escalated":
        return "human_checkpoint"
    validation = state["validation"]
    if validation is None:
        return "human_checkpoint"
    return {
        "proceed": "open_pr_node",
        "retry": "implement_node",
        "escalate": "human_checkpoint",
    }.get(validation.next_action, "human_checkpoint")


async def open_pr_node(state: RalphState) -> dict[str, Any]:
    changed_paths = [f.path for f in state["files_changed"]]
    commit_result = await commit.fn(  
        message=f"feat: {state['task'][:72]}",
        files=changed_paths,
    )
    if not commit_result.success:
        return {
            "status": "failed",
            "error_log": state["error_log"] + [f"Commit failed: {commit_result.error}"],
        }

    pr_result = await open_pr.fn(  
        title=state["task"][:72],
        body=(
            f"## Task\n{state['task']}\n\n"
            f"## Changes\n"
            + "\n".join(f"- `{f.path}` ({f.operation})" for f in state["files_changed"])
            + f"\n\n## Implementation Notes\n"
            + (state.get("impl_notes", "") or "")
        ),
    )
    if not pr_result.success:
        return {
            "status": "failed",
            "error_log": state["error_log"] + [f"PR creation failed: {pr_result.error}"],
        }

    return {
        "pr_url": pr_result.url,
        "pr_number": pr_result.number,
        "status": "reviewing",
    }


async def review_loop_node(state: RalphState) -> dict[str, Any]:
    guard = pre_node_guard(state, "review_loop_node")
    if not guard.allowed:
        return {"status": "escalated", "error_log": state["error_log"] + [guard.reason]}

    review = await run_reviewer(state["pr_number"], state["task"])
    return {
        "review": review,
        "review_iteration_count": state["review_iteration_count"] + 1,
    }


def route_after_review(state: RalphState) -> str:
    if state["status"] == "escalated":
        return "human_checkpoint"
    review = state["review"]
    if review is None or not review.approved:
        if state["review_iteration_count"] >= 3:
            return "human_checkpoint"
        return "implement_node"
    return "merge_node"


async def merge_node(state: RalphState) -> dict[str, Any]:
    result = await merge_pr.fn(pr_number=state["pr_number"])  
    if not result.success:
        return {
            "status": "failed",
            "error_log": state["error_log"] + [f"Merge failed: {result.error}"],
        }
    return {"status": "done"}


async def human_checkpoint(state: RalphState) -> dict[str, Any]:
    logfire.warning(
        "human_escalation_required",
        task=state["task"],
        iteration_count=state["iteration_count"],
        error_log=state["error_log"],
        status=state["status"],
    )
    return {"status": "escalated"}


def build_ralph_graph() -> StateGraph:
    graph = StateGraph(RalphState)

    graph.add_node("plan_node", plan_node)
    graph.add_node("implement_node", implement_node)
    graph.add_node("validate_node", validate_node)
    graph.add_node("open_pr_node", open_pr_node)
    graph.add_node("review_loop_node", review_loop_node)
    graph.add_node("merge_node", merge_node)
    graph.add_node("human_checkpoint", human_checkpoint)

    graph.set_entry_point("plan_node")
    graph.add_edge("plan_node", "implement_node")
    graph.add_edge("implement_node", "validate_node")
    graph.add_conditional_edges("validate_node", route_after_validate)
    graph.add_edge("open_pr_node", "review_loop_node")
    graph.add_conditional_edges("review_loop_node", route_after_review)
    graph.add_edge("merge_node", END)
    graph.add_edge("human_checkpoint", END)

    return graph


async def run_ralph_loop(task: str) -> RalphState:
    """Entry point: run the full Ralph Loop for a task. Returns final state."""
    start_time = time.monotonic()

    with logfire.span("ralph_loop", task=task[:100]):
        graph = build_ralph_graph()
        app = graph.compile()

        state = initial_state(task)
        final_state = await app.ainvoke(state)

        duration = time.monotonic() - start_time
        logfire.info(
            "ralph_loop_complete",
            task=task[:100],
            status=final_state["status"],
            iterations=final_state["iteration_count"],
            duration_seconds=duration,
        )

        # Emit RunMetrics
        metrics = RunMetrics(
            cost=CostSummary(
                tokens_in=0,  # TODO: wire up token counting from Logfire spans
                tokens_out=0,
                cost_usd=0.0,
                model="gemini-2.0-flash",
                task=task[:200],
                workflow="ralph_loop",
                duration_seconds=duration,
                iterations=final_state["iteration_count"],
                tool_calls=final_state["total_tool_calls"],
            ),
            per_node_costs={},
            highest_cost_node="unknown",
        )
        logfire.info("run_metrics", **metrics.model_dump())

    return final_state
