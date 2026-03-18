"""Test writer workflow node — writes adversarial tests after implementation.

Extracted from ralph_loop.py to stay under GP-002 (500 lines).
Wired into the graph between implement_node and validate_node.
"""

from typing import Any

from agents.core.context_builder import build_context
from agents.core.guards import pre_node_guard
from agents.core.state import RalphState
from agents.core.workflow_helpers import (
    accumulate_usage,
    apply_file_changes,
    retry_on_transient,
)
from agents.workers.test_writer import run_test_writer


async def test_writer_node(state: RalphState) -> dict[str, Any]:
    """Write tests for the implementation. Routes to validate_node."""
    guard = pre_node_guard(state, "test_writer_node")
    if not guard.allowed:
        return {
            "status": "escalated" if guard.action == "escalate" else "failed",
            "error_log": state["error_log"] + [guard.reason],
        }

    iteration = state["test_writer_iteration"] + 1
    context = build_context(state["task"], worker_role="test_writer")

    output, usage, tool_calls = await retry_on_transient(
        run_test_writer,
        task=state["task"],
        plan=state["plan"],
        files_changed=state["files_changed"],
        context=context,
        previous_quality=state.get("test_quality"),
        iteration=iteration,
    )

    # Apply test files to disk
    apply_file_changes(output.test_files)

    node_calls = tool_calls + 1
    return {
        "test_writer_iteration": iteration,
        "status": "validating",
        **accumulate_usage(state, usage, "test_writer_node", node_calls),
        "total_tool_calls": state["total_tool_calls"] + node_calls,
    }
