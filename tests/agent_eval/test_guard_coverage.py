"""Comprehensive guard coverage tests across all workflows.

Tests that:
1. Guards work with ReviewerState (minimal state) not just RalphState
2. Guard failures propagate correctly (set status + error_log, stop routing)
3. All node tool call tracking is consistent
4. Cost budget from ReviewerState is respected
"""

from agents.core.guards import (
    MAX_COST_USD_PER_RUN,
    MAX_IMPLEMENT_ITERATIONS,
    MAX_REVIEW_ITERATIONS,
    MAX_TOOL_CALLS_PER_NODE,
    MAX_TOTAL_TOOL_CALLS,
    GuardResult,
    check_guards,
    pre_node_guard,
)
from tests.agent_eval.conftest import make_feedback_state as _feedback_state
from tests.agent_eval.conftest import make_reviewer_state as _reviewer_state

# --- ReviewerState guard tests ---


def test_reviewer_fresh_state_allowed() -> None:
    result = check_guards(_reviewer_state())
    assert result.allowed
    assert result.action == "continue"


def test_reviewer_cost_budget_escalates() -> None:
    state = _reviewer_state(estimated_cost_usd=2.0, cost_budget_usd=2.0)
    result = check_guards(state)
    assert not result.allowed
    assert result.action == "escalate"
    assert "Cost budget" in result.reason


def test_reviewer_custom_cost_budget() -> None:
    """ReviewerState has its own cost_budget_usd field, guards should use it."""
    state = _reviewer_state(estimated_cost_usd=0.5, cost_budget_usd=0.5)
    result = check_guards(state)
    assert not result.allowed
    assert "$0.50" in result.reason


def test_reviewer_review_iterations_escalates() -> None:
    state = _reviewer_state(review_iteration_count=MAX_REVIEW_ITERATIONS)
    result = check_guards(state, node_name="review_loop_node")
    assert not result.allowed
    assert result.action == "escalate"


def test_reviewer_review_iterations_allows_non_review_node() -> None:
    """Downstream nodes must not be blocked after max review iterations."""
    state = _reviewer_state(review_iteration_count=MAX_REVIEW_ITERATIONS)
    result = check_guards(state, node_name="some_other_node")
    assert result.allowed


def test_reviewer_total_tool_calls_aborts() -> None:
    state = _reviewer_state(total_tool_calls=MAX_TOTAL_TOOL_CALLS)
    result = check_guards(state)
    assert not result.allowed
    assert result.action == "abort"


def test_reviewer_per_node_limit() -> None:
    state = _reviewer_state(
        node_tool_calls={"review_node": MAX_TOOL_CALLS_PER_NODE},
    )
    result = check_guards(state, node_name="review_node")
    assert not result.allowed
    assert "per-node" in result.reason


def test_reviewer_per_node_different_node_allowed() -> None:
    """A node at its limit shouldn't block a different node."""
    state = _reviewer_state(
        node_tool_calls={"review_node": MAX_TOOL_CALLS_PER_NODE},
    )
    result = check_guards(state, node_name="address_feedback_node")
    assert result.allowed


# --- FeedbackState guard tests ---


def test_feedback_fresh_state_allowed() -> None:
    result = check_guards(_feedback_state())
    assert result.allowed


def test_feedback_iteration_limit_escalates() -> None:
    state = _feedback_state(iteration_count=MAX_IMPLEMENT_ITERATIONS)
    result = check_guards(state, node_name="implement_feedback_node")
    assert not result.allowed
    assert result.action == "escalate"


def test_feedback_iteration_limit_allows_downstream() -> None:
    """commit_push_node must proceed after successful final implementation."""
    state = _feedback_state(iteration_count=MAX_IMPLEMENT_ITERATIONS)
    result = check_guards(state, node_name="commit_push_node")
    assert result.allowed


def test_feedback_cost_budget_escalates() -> None:
    state = _feedback_state(estimated_cost_usd=MAX_COST_USD_PER_RUN)
    result = check_guards(state)
    assert not result.allowed


def test_feedback_per_node_limit() -> None:
    state = _feedback_state(
        node_tool_calls={"implement_feedback_node": MAX_TOOL_CALLS_PER_NODE},
    )
    result = check_guards(state, node_name="implement_feedback_node")
    assert not result.allowed


# --- pre_node_guard integration ---


def test_pre_node_guard_returns_guard_result() -> None:
    state = _reviewer_state()
    result = pre_node_guard(state, "review_node")
    assert isinstance(result, GuardResult)
    assert result.allowed


def test_pre_node_guard_blocked_returns_reason() -> None:
    state = _reviewer_state(total_tool_calls=MAX_TOTAL_TOOL_CALLS)
    result = pre_node_guard(state, "review_node")
    assert not result.allowed
    assert result.reason is not None
    assert "Tool call budget" in result.reason


# --- Guard priority tests ---


def test_per_node_checked_before_global_limits() -> None:
    """Per-node limit should fire before checking iteration/cost limits."""
    state = _reviewer_state(
        node_tool_calls={"review_node": MAX_TOOL_CALLS_PER_NODE},
        review_iteration_count=MAX_REVIEW_ITERATIONS,
    )
    result = check_guards(state, node_name="review_node")
    assert not result.allowed
    assert "per-node" in result.reason


def test_iteration_checked_before_cost() -> None:
    """Iteration limit should fire before cost limit on review nodes."""
    state = _reviewer_state(
        review_iteration_count=MAX_REVIEW_ITERATIONS,
        estimated_cost_usd=MAX_COST_USD_PER_RUN,
    )
    result = check_guards(state, node_name="review_loop_node")
    assert not result.allowed
    assert "review iterations" in result.reason


# --- State without optional fields (minimal dict) ---


def test_minimal_dict_state_allowed() -> None:
    """Guards should work with a bare dict missing most fields."""
    result = check_guards({})
    assert result.allowed


def test_minimal_dict_with_cost_over_budget() -> None:
    result = check_guards({"estimated_cost_usd": 5.0})
    assert not result.allowed
    assert result.action == "escalate"


# --- reply_node mid-loop guard enforcement ---


def test_reply_node_mid_loop_guard_breaks_at_limit() -> None:
    """reply_node must enforce MAX_TOOL_CALLS_PER_NODE mid-loop.

    Simulates mid-loop check: entry guard passes with (limit - 2) calls,
    but after 2 more calls the per-node guard must fire.
    """
    existing = MAX_TOOL_CALLS_PER_NODE - 2
    state = _feedback_state(node_tool_calls={"reply_node": existing})
    result = pre_node_guard(state, "reply_node")
    assert result.allowed

    state["node_tool_calls"]["reply_node"] = existing + 2
    result = check_guards(state, node_name="reply_node")
    assert not result.allowed
    assert "per-node" in result.reason


def test_reply_node_fresh_state_allows_up_to_limit() -> None:
    """With no prior calls, reply_node guard allows entry."""
    state = _feedback_state(node_tool_calls={"reply_node": 0})
    result = pre_node_guard(state, "reply_node")
    assert result.allowed

    state["node_tool_calls"]["reply_node"] = MAX_TOOL_CALLS_PER_NODE
    result = check_guards(state, node_name="reply_node")
    assert not result.allowed
