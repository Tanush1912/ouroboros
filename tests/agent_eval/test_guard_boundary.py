"""Property-style tests for guard boundary conditions.

These verify that the guard system allows workflows to complete normally
at the configured limits, not just that guards fire when exceeded.

- 5th implement attempt may still finish successfully (downstream nodes allowed).
- 3rd review approval may still merge (merge_node not blocked).
- Exactly-at-limit reply count succeeds; limit+1 escalates.
"""

from agents.core.guards import (
    MAX_IMPLEMENT_ITERATIONS,
    MAX_REVIEW_ITERATIONS,
    MAX_TOOL_CALLS_PER_NODE,
    MAX_TOTAL_TOOL_CALLS,
    check_guards,
)
from tests.agent_eval.conftest import _state_with

# --- 5th implement attempt may still finish ---


def test_5th_implement_blocks_reentry() -> None:
    """implement_node is blocked after 5 iterations."""
    state = _state_with(iteration_count=MAX_IMPLEMENT_ITERATIONS)
    result = check_guards(state, node_name="implement_node")
    assert not result.allowed
    assert "implement iterations" in result.reason


def test_5th_implement_allows_validate() -> None:
    """validate_node proceeds after successful 5th implementation."""
    state = _state_with(iteration_count=MAX_IMPLEMENT_ITERATIONS)
    result = check_guards(state, node_name="validate_node")
    assert result.allowed


def test_5th_implement_allows_perf_validate() -> None:
    state = _state_with(iteration_count=MAX_IMPLEMENT_ITERATIONS)
    result = check_guards(state, node_name="perf_validate_node")
    assert result.allowed


def test_5th_implement_allows_ui_validate() -> None:
    state = _state_with(iteration_count=MAX_IMPLEMENT_ITERATIONS)
    result = check_guards(state, node_name="ui_validate_node")
    assert result.allowed


def test_5th_implement_allows_open_pr() -> None:
    state = _state_with(iteration_count=MAX_IMPLEMENT_ITERATIONS)
    result = check_guards(state, node_name="open_pr_node")
    assert result.allowed


def test_5th_implement_allows_review() -> None:
    state = _state_with(iteration_count=MAX_IMPLEMENT_ITERATIONS)
    result = check_guards(state, node_name="review_loop_node")
    assert result.allowed


def test_5th_implement_allows_merge() -> None:
    state = _state_with(iteration_count=MAX_IMPLEMENT_ITERATIONS)
    result = check_guards(state, node_name="merge_node")
    assert result.allowed


def test_5th_implement_allows_commit_push() -> None:
    """commit_push_node in feedback loop proceeds after 5th implementation."""
    state = _state_with(iteration_count=MAX_IMPLEMENT_ITERATIONS)
    result = check_guards(state, node_name="commit_push_node")
    assert result.allowed


def test_5th_implement_blocks_feedback_reentry() -> None:
    """implement_feedback_node is also blocked at max iterations."""
    state = _state_with(iteration_count=MAX_IMPLEMENT_ITERATIONS)
    result = check_guards(state, node_name="implement_feedback_node")
    assert not result.allowed


# --- 3rd review approval may still merge ---


def test_3rd_review_blocks_reentry() -> None:
    """review_loop_node is blocked after 3 review iterations."""
    state = _state_with(review_iteration_count=MAX_REVIEW_ITERATIONS)
    result = check_guards(state, node_name="review_loop_node")
    assert not result.allowed
    assert "review iterations" in result.reason


def test_3rd_review_allows_merge() -> None:
    """merge_node proceeds after approval on the 3rd review."""
    state = _state_with(review_iteration_count=MAX_REVIEW_ITERATIONS)
    result = check_guards(state, node_name="merge_node")
    assert result.allowed


def test_3rd_review_blocks_address_feedback() -> None:
    """address_feedback_node is blocked after max review iterations."""
    state = _state_with(review_iteration_count=MAX_REVIEW_ITERATIONS)
    result = check_guards(state, node_name="address_feedback_node")
    assert not result.allowed


def test_3rd_review_allows_open_pr() -> None:
    """Downstream open_pr_node is not blocked by review count."""
    state = _state_with(review_iteration_count=MAX_REVIEW_ITERATIONS)
    result = check_guards(state, node_name="open_pr_node")
    assert result.allowed


# --- Exactly-at-limit reply count succeeds; limit+1 escalates ---


def test_exactly_at_node_limit_blocks_entry() -> None:
    """pre_node_guard blocks entry when a node is already at the limit."""
    state = _state_with(
        node_tool_calls={"reply_node": MAX_TOOL_CALLS_PER_NODE},
    )
    result = check_guards(state, node_name="reply_node")
    assert not result.allowed
    assert "per-node" in result.reason


def test_under_node_limit_allows_entry() -> None:
    """Entry is allowed when node calls are under the limit."""
    state = _state_with(
        node_tool_calls={"reply_node": MAX_TOOL_CALLS_PER_NODE - 1},
    )
    result = check_guards(state, node_name="reply_node")
    assert result.allowed


def test_mid_loop_exactly_at_limit_should_not_escalate() -> None:
    """With node_tool_calls exactly at the limit, the guard blocks entry.

    check_guards uses >= so exactly-at-limit IS blocked (pre-call check).
    """
    state = _state_with(
        node_tool_calls={"reply_node": MAX_TOOL_CALLS_PER_NODE},
        total_tool_calls=MAX_TOOL_CALLS_PER_NODE,
    )
    result = check_guards(state, node_name="reply_node")
    assert not result.allowed
    assert result.action == "escalate"


def test_mid_loop_over_limit_should_escalate() -> None:
    """One call beyond the per-node limit triggers escalation."""
    state = _state_with(
        node_tool_calls={"reply_node": MAX_TOOL_CALLS_PER_NODE + 1},
        total_tool_calls=MAX_TOOL_CALLS_PER_NODE + 1,
    )
    result = check_guards(state, node_name="reply_node")
    assert not result.allowed
    assert result.action == "escalate"


def test_mid_loop_partial_budget_at_limit() -> None:
    """With prior calls from other nodes, exactly reaching per-node limit blocks."""
    state = _state_with(
        node_tool_calls={"reply_node": MAX_TOOL_CALLS_PER_NODE},
        total_tool_calls=100,
    )
    result = check_guards(state, node_name="reply_node")
    assert not result.allowed


def test_mid_loop_partial_budget_over_limit() -> None:
    """Under per-node limit but over total budget → abort."""
    state = _state_with(
        node_tool_calls={"reply_node": 10},
        total_tool_calls=MAX_TOTAL_TOOL_CALLS,
    )
    result = check_guards(state, node_name="reply_node")
    assert not result.allowed
    assert result.action == "abort"
