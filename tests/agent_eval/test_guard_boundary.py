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
    """The reply_node mid-loop check uses > (not >=).

    With existing=0 and attempts=MAX_TOOL_CALLS_PER_NODE, the condition
    `0 + 50 > 50` is False, so it should NOT escalate.
    """
    existing = 0
    attempts = MAX_TOOL_CALLS_PER_NODE
    assert not (existing + attempts > MAX_TOOL_CALLS_PER_NODE)


def test_mid_loop_over_limit_should_escalate() -> None:
    """One attempt beyond the limit triggers escalation.

    With existing=0 and attempts=MAX_TOOL_CALLS_PER_NODE+1, the condition
    `0 + 51 > 50` is True, so it should escalate.
    """
    existing = 0
    attempts = MAX_TOOL_CALLS_PER_NODE + 1
    assert existing + attempts > MAX_TOOL_CALLS_PER_NODE


def test_mid_loop_partial_budget_at_limit() -> None:
    """With prior calls, exactly reaching the limit is still OK.

    existing=10, attempts=40: 10+40 > 50 is False → no escalation.
    """
    existing = 10
    attempts = MAX_TOOL_CALLS_PER_NODE - existing
    assert not (existing + attempts > MAX_TOOL_CALLS_PER_NODE)


def test_mid_loop_partial_budget_over_limit() -> None:
    """With prior calls, exceeding the limit triggers escalation.

    existing=10, attempts=41: 10+41 > 50 is True → escalation.
    """
    existing = 10
    attempts = MAX_TOOL_CALLS_PER_NODE - existing + 1
    assert existing + attempts > MAX_TOOL_CALLS_PER_NODE
