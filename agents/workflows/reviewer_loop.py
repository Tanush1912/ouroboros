"""Reviewer Loop — agent-to-agent review workflow.

Runs reviewer against a PR, collects feedback, routes to implementer
to address change requests, then re-reviews. Max MAX_REVIEW_ITERATIONS cycles.
"""

from typing import TypedDict

import logfire
from langgraph.graph import END, StateGraph

from agents.core.guards import MAX_REVIEW_ITERATIONS, pre_node_guard
from agents.core.workflow_helpers import accumulate_usage, apply_file_changes
from agents.models.planner import ExecutionStep, PlanOutput
from agents.models.reviewer import ReviewOutput
from agents.workers.implementer import run_implementer
from agents.workers.reviewer import run_reviewer


class ReviewerState(TypedDict):
    pr_number: int
    task: str
    review: ReviewOutput | None
    review_iteration_count: int
    resolved: bool
    status: str
    error_log: list[str]
    estimated_cost_usd: float
    cost_budget_usd: float
    total_tool_calls: int
    total_tokens_in: int
    total_tokens_out: int
    node_tool_calls: dict[str, int]
    node_token_usage: dict[str, dict[str, int]]


async def review_node(state: ReviewerState) -> dict:
    guard = pre_node_guard(state, "review_node")
    if not guard.allowed:
        return {"status": "failed", "error_log": state["error_log"] + [guard.reason]}

    review, usage = await run_reviewer(state["pr_number"], state["task"])
    node_calls = 1
    return {
        "review": review,
        "review_iteration_count": state["review_iteration_count"] + 1,
        "resolved": review.approved,
        **accumulate_usage(state, usage, "review_node", node_calls),
        "total_tool_calls": state["total_tool_calls"] + node_calls,
    }


async def address_feedback_node(state: ReviewerState) -> dict:
    """Run the implementer to address blocking review feedback, then re-review."""
    guard = pre_node_guard(state, "address_feedback_node")
    if not guard.allowed:
        return {"status": "failed", "error_log": state["error_log"] + [guard.reason]}

    review = state["review"]
    if not review or not review.blocking_issues:
        return {}

    feedback_task = (
        f"Address review feedback for: {state['task']}\n\n"
        f"Blocking issues:\n" + "\n".join(f"- {issue}" for issue in review.blocking_issues)
    )
    feedback_plan = PlanOutput(
        task_summary=f"Address review feedback ({len(review.blocking_issues)} blocking issues)",
        steps=[
            ExecutionStep(
                description=issue,
                files_affected=[],
                tool="fs",
            )
            for issue in review.blocking_issues
        ],
        test_strategy="Re-run reviewer after changes",
        risk_level="low",
        requires_human_review=False,
    )

    impl, usage, tool_calls = await run_implementer(
        task=feedback_task,
        plan=feedback_plan,
        iteration=state["review_iteration_count"],
    )

    apply_file_changes(impl.files_changed)

    node_calls = tool_calls + 1
    logfire.info(
        "address_feedback_complete",
        files_changed=len(impl.files_changed),
        blocking_issues=len(review.blocking_issues),
    )

    return {
        **accumulate_usage(state, usage, "address_feedback_node", node_calls),
        "total_tool_calls": state["total_tool_calls"] + node_calls,
    }


def route_review(state: ReviewerState) -> str:
    if state.get("status") == "failed":
        return "escalate"
    if state["resolved"]:
        return "approved"
    if state["review_iteration_count"] >= MAX_REVIEW_ITERATIONS:
        return "escalate"
    return "address_feedback"


def _reviewer_status_gate(state: ReviewerState, next_node: str) -> str:
    """Route to END on failure, otherwise continue."""
    if state.get("status") == "failed":
        return END
    return next_node


def route_after_address(state: ReviewerState) -> str:
    return _reviewer_status_gate(state, "review_node")


def build_reviewer_graph() -> StateGraph:
    graph = StateGraph(ReviewerState)
    graph.add_node("review_node", review_node)
    graph.add_node("address_feedback_node", address_feedback_node)
    graph.add_conditional_edges(
        "review_node",
        route_review,
        {"approved": END, "escalate": END, "address_feedback": "address_feedback_node"},
    )
    graph.add_conditional_edges(
        "address_feedback_node",
        route_after_address,
        {"review_node": "review_node", END: END},
    )
    graph.set_entry_point("review_node")
    return graph


async def run_reviewer_loop(pr_number: int, task: str) -> ReviewerState:
    """Run the reviewer loop for a PR. Returns final state with review outcome."""
    with logfire.span("reviewer_loop", pr_number=pr_number):
        graph = build_reviewer_graph()
        app = graph.compile()
        state = ReviewerState(
            pr_number=pr_number,
            task=task,
            review=None,
            review_iteration_count=0,
            resolved=False,
            status="reviewing",
            error_log=[],
            estimated_cost_usd=0.0,
            cost_budget_usd=2.0,
            total_tool_calls=0,
            total_tokens_in=0,
            total_tokens_out=0,
            node_tool_calls={},
            node_token_usage={},
        )
        final = await app.ainvoke(state)
        logfire.info(
            "reviewer_loop_complete",
            pr_number=pr_number,
            approved=final["resolved"],
            iterations=final["review_iteration_count"],
            cost_usd=final["estimated_cost_usd"],
        )
        return final
