"""Ralph Loop routing functions — status-aware conditional edges.

Extracted from ralph_loop.py to stay under GP-002 (500 lines).
Each function checks state["status"] and routes to human_checkpoint
on failure/escalation.
"""

from langgraph.graph import END

from agents.core.guards import MAX_REVIEW_ITERATIONS
from agents.core.state import RalphState

_BUG_FIX_KEYWORDS = frozenset({"fix", "bug", "error", "broken", "failing", "crash"})


def route_after_plan(state: RalphState) -> str:
    """Route to reproduce_node for bug-fix tasks, otherwise straight to implement."""
    if state["status"] == "escalated":
        return "human_checkpoint"

    has_prior_failure = state["validation"] is not None and not state["validation"].overall_pass
    task_lower = state["task"].lower()
    has_bug_keywords = any(kw in task_lower for kw in _BUG_FIX_KEYWORDS)

    if has_prior_failure or has_bug_keywords:
        return "reproduce_node"
    return "implement_node"


def route_after_validate(state: RalphState) -> str:
    if state["status"] == "escalated":
        return "human_checkpoint"
    validation = state["validation"]
    if validation is None:
        return "human_checkpoint"
    route_map = {
        "proceed": "perf_validate_node",
        "retry": "implement_node",
        "escalate": "human_checkpoint",
    }
    return route_map[validation.next_action]


def route_after_review(state: RalphState) -> str:
    if state["status"] == "escalated":
        return "human_checkpoint"
    review = state["review"]
    if review is None or not review.approved or not review.has_meaningful_tests:
        if state["review_iteration_count"] >= MAX_REVIEW_ITERATIONS:
            return "human_checkpoint"
        return "implement_node"
    return "merge_node"


def _ralph_status_gate(state: RalphState, next_node: str) -> str:
    """Route to human_checkpoint on failure/escalation, otherwise continue."""
    if state.get("status") in ("failed", "escalated"):
        return "human_checkpoint"
    return next_node


def route_after_implement(state: RalphState) -> str:
    return _ralph_status_gate(state, "validate_node")


def route_after_reproduce(state: RalphState) -> str:
    return _ralph_status_gate(state, "implement_node")


def route_after_perf_validate(state: RalphState) -> str:
    return _ralph_status_gate(state, "ui_validate_node")


def route_after_ui_validate(state: RalphState) -> str:
    return _ralph_status_gate(state, "open_pr_node")


def route_after_open_pr(state: RalphState) -> str:
    return _ralph_status_gate(state, "review_loop_node")


def route_after_merge(state: RalphState) -> str:
    if state.get("status") in ("failed", "escalated"):
        return "human_checkpoint"
    return END
