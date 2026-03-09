"""Shared workflow helpers — DRY utilities used by all LangGraph workflows.

Centralizes file-change application, token/cost accumulation, and per-node
tool call tracking so orchestration nodes don't repeat this logic.
"""

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from agents.core.paths import repo_root as _repo_root
from agents.models.cost import TokenUsage
from agents.models.implementer import FileChange


def apply_file_changes(changes: list[FileChange], root: Path | None = None) -> None:
    """Apply a list of FileChange objects to disk.

    Creates parent directories as needed. Handles create, modify, and delete operations.
    """
    if root is None:
        root = _repo_root()
    for change in changes:
        target = root / change.path
        if change.operation == "delete":
            target.unlink(missing_ok=True)
        elif change.content is not None:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(change.content, encoding="utf-8")


def accumulate_usage(
    state: Mapping[str, Any], usage: TokenUsage, node_name: str, tool_calls: int = 0
) -> dict[str, Any]:
    """Return state updates for token/cost accumulation, including per-node tracking.

    Works with any workflow state dict (RalphState, FeedbackState, etc.).
    """
    prev = state.get("node_token_usage", {}).get(node_name, {"tokens_in": 0, "tokens_out": 0})
    updated_node_usage = dict(state.get("node_token_usage", {}))
    updated_node_usage[node_name] = {
        "tokens_in": prev["tokens_in"] + usage.tokens_in,
        "tokens_out": prev["tokens_out"] + usage.tokens_out,
    }
    updated_ntc = dict(state.get("node_tool_calls", {}))
    updated_ntc[node_name] = updated_ntc.get(node_name, 0) + tool_calls
    return {
        "total_tokens_in": state.get("total_tokens_in", 0) + usage.tokens_in,
        "total_tokens_out": state.get("total_tokens_out", 0) + usage.tokens_out,
        "estimated_cost_usd": state.get("estimated_cost_usd", 0) + usage.cost_usd(),
        "node_token_usage": updated_node_usage,
        "node_tool_calls": updated_ntc,
    }


def update_node_tool_calls(state: Mapping[str, Any], node_name: str, calls: int) -> dict[str, int]:
    """Return updated node_tool_calls dict with additional calls for a node."""
    updated = dict(state.get("node_tool_calls", {}))
    updated[node_name] = updated.get(node_name, 0) + calls
    return updated
