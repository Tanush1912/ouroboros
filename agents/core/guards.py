"""Rate-limit and iteration guards.

Hard limits enforced at every LangGraph node across all workflows.
These are constants, not config — intentionally not tunable at runtime.
When limits are hit, escalate to human checkpoint.

These guards run via the pre_node_guard wrapper on every node entry.
Works with any state dict (RalphState, FeedbackState, ReviewerState)
by using .get() with defaults for optional fields.

Iteration guards only block re-entry into the nodes that perform the
iteration (implement / review nodes), not downstream success nodes.
"""

from collections.abc import Mapping
from typing import Any, Literal

from pydantic import BaseModel

MAX_IMPLEMENT_ITERATIONS = 5
MAX_REVIEW_ITERATIONS = 3
MAX_TOOL_CALLS_PER_NODE = 50
MAX_TOTAL_TOOL_CALLS = 200
MAX_COST_USD_PER_RUN = 2.00

_IMPLEMENT_NODES = frozenset({"implement_node", "implement_feedback_node"})
_REVIEW_NODES = frozenset({"review_loop_node", "address_feedback_node"})


class GuardResult(BaseModel):
    allowed: bool
    reason: str | None = None
    action: Literal["continue", "escalate", "abort"]


def check_guards(state: Mapping[str, Any], node_name: str | None = None) -> GuardResult:
    """Check all guards. Returns the first violation found, or allowed=True.

    Works with any state dict — uses .get() with defaults for fields that
    may not exist in all state types (e.g. ReviewerState lacks iteration_count).
    """
    if node_name is not None:
        node_calls = state.get("node_tool_calls", {}).get(node_name, 0)
        if node_calls >= MAX_TOOL_CALLS_PER_NODE:
            return GuardResult(
                allowed=False,
                reason=(
                    f"Node '{node_name}' hit per-node tool call limit "
                    f"({MAX_TOOL_CALLS_PER_NODE}). Escalating."
                ),
                action="escalate",
            )

    if (
        node_name in _IMPLEMENT_NODES
        and state.get("iteration_count", 0) >= MAX_IMPLEMENT_ITERATIONS
    ):
        return GuardResult(
            allowed=False,
            reason=(
                f"Max implement iterations reached ({MAX_IMPLEMENT_ITERATIONS}). "
                "Cannot retry — escalating to human checkpoint."
            ),
            action="escalate",
        )

    if (
        node_name in _REVIEW_NODES
        and state.get("review_iteration_count", 0) >= MAX_REVIEW_ITERATIONS
    ):
        return GuardResult(
            allowed=False,
            reason=(
                f"Max review iterations reached ({MAX_REVIEW_ITERATIONS}). "
                "Cannot address more review feedback — escalating."
            ),
            action="escalate",
        )

    if state.get("total_tool_calls", 0) >= MAX_TOTAL_TOOL_CALLS:
        return GuardResult(
            allowed=False,
            reason=(
                f"Tool call budget exhausted ({MAX_TOTAL_TOOL_CALLS} total calls). "
                "Aborting workflow run."
            ),
            action="abort",
        )

    budget = state.get("cost_budget_usd", MAX_COST_USD_PER_RUN)
    if state.get("estimated_cost_usd", 0) >= budget:
        return GuardResult(
            allowed=False,
            reason=f"Cost budget ${budget:.2f} reached — escalating.",
            action="escalate",
        )

    return GuardResult(allowed=True, action="continue")


def pre_node_guard(state: Mapping[str, Any], node_name: str) -> GuardResult:
    """Wrapper called at the entry of every LangGraph node.

    Works with any workflow state type (RalphState, FeedbackState, ReviewerState).
    """
    result = check_guards(state, node_name=node_name)
    if not result.allowed:
        import logfire

        logfire.warning(
            "Guard triggered",
            node=node_name,
            reason=result.reason,
            action=result.action,
            iteration_count=state.get("iteration_count", 0),
            total_tool_calls=state.get("total_tool_calls", 0),
        )
    return result
