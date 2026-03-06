"""Reviewer Loop — agent-to-agent review workflow.

Runs reviewer against a PR, collects feedback, routes to implementer
to address change requests, then re-reviews. Max MAX_REVIEW_ITERATIONS cycles.
"""

from typing import TypedDict

import logfire
from langgraph.graph import END, StateGraph

from agents.core.guards import MAX_REVIEW_ITERATIONS
from agents.models.planner import ExecutionStep, PlanOutput
from agents.models.reviewer import ReviewOutput
from agents.workers.implementer import run_implementer
from agents.workers.reviewer import run_reviewer


class ReviewerState(TypedDict):
    pr_number: int
    task: str
    review: ReviewOutput | None
    iteration: int
    resolved: bool
    estimated_cost_usd: float


async def review_node(state: ReviewerState) -> dict:
    review, usage = await run_reviewer(state["pr_number"], state["task"])
    return {
        "review": review,
        "iteration": state["iteration"] + 1,
        "resolved": review.approved,
        "estimated_cost_usd": state["estimated_cost_usd"] + usage.cost_usd(),
    }


async def address_feedback_node(state: ReviewerState) -> dict:
    """Run the implementer to address blocking review feedback, then re-review."""
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

    impl, usage = await run_implementer(
        task=feedback_task,
        plan=feedback_plan,
        iteration=state["iteration"],
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

    logfire.info(
        "address_feedback_complete",
        files_changed=len(impl.files_changed),
        blocking_issues=len(review.blocking_issues),
    )

    return {
        "estimated_cost_usd": state["estimated_cost_usd"] + usage.cost_usd(),
    }


def route_review(state: ReviewerState) -> str:
    if state["resolved"]:
        return "approved"
    if state["iteration"] >= MAX_REVIEW_ITERATIONS:
        return "escalate"
    return "address_feedback"


def build_reviewer_graph() -> StateGraph:
    graph = StateGraph(ReviewerState)
    graph.add_node("review_node", review_node)
    graph.add_node("address_feedback_node", address_feedback_node)
    graph.add_conditional_edges(
        "review_node",
        route_review,
        {"approved": END, "escalate": END, "address_feedback": "address_feedback_node"},
    )
    graph.add_edge("address_feedback_node", "review_node")
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
            iteration=0,
            resolved=False,
            estimated_cost_usd=0.0,
        )
        final = await app.ainvoke(state)
        logfire.info(
            "reviewer_loop_complete",
            pr_number=pr_number,
            approved=final["resolved"],
            iterations=final["iteration"],
            cost_usd=final["estimated_cost_usd"],
        )
        return final
