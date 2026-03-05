"""Reviewer Loop — agent-to-agent review workflow.

Runs reviewer against a PR, collects feedback, loops back to implementer
if there are blocking issues. Max MAX_REVIEW_ITERATIONS cycles.
"""

from typing import TypedDict

import logfire
from langgraph.graph import END, StateGraph

from agents.core.guards import MAX_REVIEW_ITERATIONS
from agents.models.reviewer import ReviewOutput
from agents.workers.reviewer import run_reviewer


class ReviewerState(TypedDict):
    pr_number: int
    task: str
    review: ReviewOutput | None
    iteration: int
    resolved: bool


async def review_node(state: ReviewerState) -> dict:
    review, _ = await run_reviewer(state["pr_number"], state["task"])
    return {
        "review": review,
        "iteration": state["iteration"] + 1,
        "resolved": review.approved,
    }


def route_review(state: ReviewerState) -> str:
    if state["resolved"]:
        return "approved"
    if state["iteration"] >= MAX_REVIEW_ITERATIONS:
        return "escalate"
    return "continue_review"


def build_reviewer_graph() -> StateGraph:
    graph = StateGraph(ReviewerState)
    graph.add_node("review_node", review_node)
    graph.add_conditional_edges(
        "review_node",
        route_review,
        {"approved": END, "escalate": END, "continue_review": "review_node"},
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
            iteration=0,
            resolved=False,
        )
        final = await app.ainvoke(state)
        logfire.info(
            "reviewer_loop_complete",
            pr_number=pr_number,
            approved=final["resolved"],
            iterations=final["iteration"],
        )
        return final
