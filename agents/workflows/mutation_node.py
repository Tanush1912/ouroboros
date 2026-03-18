"""Mutation sampling workflow node — verifies test effectiveness.

Extracted from ralph_loop.py to stay under GP-002 (500 lines).
Runs after validate_node passes, before perf_validate_node.
"""

from typing import Any

import logfire

from agents.core.guards import pre_node_guard
from agents.core.state import RalphState
from agents.core.workflow_helpers import update_node_tool_calls
from agents.tools.mutation_sampler import run_mutation_sampling


async def mutation_validate_node(state: RalphState) -> dict[str, Any]:
    """Run mutation sampling on changed files. Routes based on kill rate."""
    guard = pre_node_guard(state, "mutation_validate_node")
    if not guard.allowed:
        return {"status": "escalated", "error_log": state["error_log"] + [guard.reason]}

    # Note: skip logic is now handled by routing (skip_stages).
    # This node only runs when the planner says it should.
    result = run_mutation_sampling(state["files_changed"])
    node_calls = result.total_mutants + 1  # Each mutation = 1 pytest run + 1 for the sampler

    logfire.info(
        "mutation_sampling_complete",
        total=result.total_mutants,
        killed=result.killed,
        survived=result.survived,
        kill_rate=result.kill_rate,
        passed=result.passed,
    )

    return {
        "mutation_result": result,
        "total_tool_calls": state["total_tool_calls"] + node_calls,
        "node_tool_calls": update_node_tool_calls(state, "mutation_validate_node", node_calls),
    }
