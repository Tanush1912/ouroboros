"""Rate-limit and iteration guards.

Hard limits enforced at every LangGraph node. These are constants, not config —
intentionally not tunable at runtime. When limits are hit, escalate to human checkpoint.

These guards run via the pre_node_guard wrapper on every node entry.
"""

from typing import Literal

from pydantic import BaseModel

from agents.core.state import RalphState

MAX_IMPLEMENT_ITERATIONS = 5
MAX_REVIEW_ITERATIONS = 3
MAX_TOOL_CALLS_PER_NODE = 50
MAX_TOTAL_TOOL_CALLS = 200
MAX_COST_USD_PER_RUN = 2.00


class GuardResult(BaseModel):
    allowed: bool
    reason: str | None = None
    action: Literal["continue", "escalate", "abort"]


def check_guards(state: RalphState) -> GuardResult:
    """Check all guards. Returns the first violation found, or allowed=True."""

    if state["iteration_count"] >= MAX_IMPLEMENT_ITERATIONS:
        return GuardResult(
            allowed=False,
            reason=(
                f"Max implement iterations reached ({MAX_IMPLEMENT_ITERATIONS}). "
                "Cannot retry — escalating to human checkpoint."
            ),
            action="escalate",
        )

    if state["review_iteration_count"] >= MAX_REVIEW_ITERATIONS:
        return GuardResult(
            allowed=False,
            reason=(
                f"Max review iterations reached ({MAX_REVIEW_ITERATIONS}). "
                "Cannot address more review feedback — escalating."
            ),
            action="escalate",
        )

    if state["total_tool_calls"] >= MAX_TOTAL_TOOL_CALLS:
        return GuardResult(
            allowed=False,
            reason=(
                f"Tool call budget exhausted ({MAX_TOTAL_TOOL_CALLS} total calls). "
                "Aborting workflow run."
            ),
            action="abort",
        )

    budget = state["cost_budget_usd"]
    if state["estimated_cost_usd"] >= budget:
        return GuardResult(
            allowed=False,
            reason=f"Cost budget ${budget:.2f} reached — escalating.",
            action="escalate",
        )

    return GuardResult(allowed=True, action="continue")


def pre_node_guard(state: RalphState, node_name: str) -> GuardResult:
    """Wrapper called at the entry of every LangGraph node."""
    result = check_guards(state)
    if not result.allowed:
        import logfire

        logfire.warning(
            "Guard triggered",
            node=node_name,
            reason=result.reason,
            action=result.action,
            iteration_count=state["iteration_count"],
            total_tool_calls=state["total_tool_calls"],
        )
    return result
