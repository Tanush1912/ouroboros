"""Tests for guard enforcement logic."""

from agents.core.guards import (
    MAX_COST_USD_PER_RUN,
    MAX_IMPLEMENT_ITERATIONS,
    MAX_REVIEW_ITERATIONS,
    MAX_TOOL_CALLS_PER_NODE,
    MAX_TOTAL_TOOL_CALLS,
    check_guards,
)
from agents.core.state import initial_state
from tests.agent_eval.conftest import _state_with


def test_fresh_state_allowed() -> None:
    result = check_guards(initial_state("test"))
    assert result.allowed
    assert result.action == "continue"


def test_max_implement_iterations_escalates() -> None:
    state = _state_with(iteration_count=MAX_IMPLEMENT_ITERATIONS)
    result = check_guards(state, node_name="implement_node")
    assert not result.allowed
    assert result.action == "escalate"
    assert "implement iterations" in result.reason


def test_max_implement_iterations_allows_downstream() -> None:
    """After a successful final iteration, downstream nodes must proceed."""
    state = _state_with(iteration_count=MAX_IMPLEMENT_ITERATIONS)
    result = check_guards(state, node_name="validate_node")
    assert result.allowed


def test_max_review_iterations_escalates() -> None:
    state = _state_with(review_iteration_count=MAX_REVIEW_ITERATIONS)
    result = check_guards(state, node_name="review_loop_node")
    assert not result.allowed
    assert result.action == "escalate"
    assert "review iterations" in result.reason


def test_max_review_iterations_allows_merge() -> None:
    """PR approved on the last review cycle must be allowed to merge."""
    state = _state_with(review_iteration_count=MAX_REVIEW_ITERATIONS)
    result = check_guards(state, node_name="merge_node")
    assert result.allowed


def test_tool_call_budget_aborts() -> None:
    state = _state_with(total_tool_calls=MAX_TOTAL_TOOL_CALLS)
    result = check_guards(state)
    assert not result.allowed
    assert result.action == "abort"
    assert "Tool call budget" in result.reason


def test_cost_budget_escalates() -> None:
    state = _state_with(estimated_cost_usd=MAX_COST_USD_PER_RUN)
    result = check_guards(state)
    assert not result.allowed
    assert result.action == "escalate"
    assert "Cost budget" in result.reason


def test_under_budget_allowed() -> None:
    state = _state_with(
        iteration_count=MAX_IMPLEMENT_ITERATIONS - 1,
        total_tool_calls=MAX_TOTAL_TOOL_CALLS - 1,
        estimated_cost_usd=MAX_COST_USD_PER_RUN - 0.01,
    )
    result = check_guards(state, node_name="implement_node")
    assert result.allowed


def test_per_node_tool_calls_escalates() -> None:
    state = _state_with(
        node_tool_calls={"implement_node": MAX_TOOL_CALLS_PER_NODE},
    )
    result = check_guards(state, node_name="implement_node")
    assert not result.allowed
    assert result.action == "escalate"
    assert "per-node tool call limit" in result.reason


def test_per_node_tool_calls_under_limit_allowed() -> None:
    state = _state_with(
        node_tool_calls={"implement_node": MAX_TOOL_CALLS_PER_NODE - 1},
    )
    result = check_guards(state, node_name="implement_node")
    assert result.allowed
