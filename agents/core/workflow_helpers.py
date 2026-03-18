"""Shared workflow helpers — DRY utilities used by all LangGraph workflows.

Centralizes file-change application, token/cost accumulation, per-node
tool call tracking, and transient error retry so orchestration nodes
don't repeat this logic.
"""

import asyncio
import logging
from collections.abc import Callable, Coroutine, Mapping
from pathlib import Path
from typing import Any

from agents.core.paths import repo_root as _repo_root
from agents.models.cost import TokenUsage
from agents.models.implementer import FileChange

_logger = logging.getLogger(__name__)

_MAX_RETRIES = 3
_RETRY_BACKOFF = (2, 5, 10)

# Import actual exception types for robust matching (not string-based).
try:
    from httpx import (
        ConnectError,
        ConnectTimeout,
        PoolTimeout,
        ReadError,
        ReadTimeout,
        RemoteProtocolError,
    )

    _TRANSIENT_HTTP_TYPES: tuple[type[Exception], ...] = (
        ReadError,
        ConnectError,
        RemoteProtocolError,
        ConnectTimeout,
        ReadTimeout,
        PoolTimeout,
    )
except ImportError:
    _TRANSIENT_HTTP_TYPES = ()

try:
    from pydantic_ai.exceptions import ModelHTTPError as _ModelHTTPError
except ImportError:
    _ModelHTTPError = None  # type: ignore[assignment,misc]


async def retry_on_transient[T](
    fn: Callable[..., Coroutine[Any, Any, T]],
    *args: Any,
    **kwargs: Any,
) -> T:
    """Retry an async function on transient HTTP/network errors.

    Catches httpx transport errors and PydanticAI ModelHTTPError with 5xx status.
    Retries up to 3 times with backoff (2s, 5s, 10s).
    """
    for attempt in range(_MAX_RETRIES):
        try:
            return await fn(*args, **kwargs)
        except Exception as exc:
            is_transient = isinstance(exc, _TRANSIENT_HTTP_TYPES)
            if (
                not is_transient
                and _ModelHTTPError is not None
                and isinstance(exc, _ModelHTTPError)
            ):
                is_transient = getattr(exc, "status_code", 0) >= 500

            if not is_transient or attempt == _MAX_RETRIES - 1:
                raise

            backoff = _RETRY_BACKOFF[attempt]
            _logger.warning(
                "Transient error (attempt %d/%d), retrying in %ds: %s",
                attempt + 1,
                _MAX_RETRIES,
                backoff,
                exc,
            )
            await asyncio.sleep(backoff)


def apply_file_changes(changes: list[FileChange], root: Path | None = None) -> None:
    """Apply a list of FileChange objects to disk.

    Creates parent directories as needed. Handles create, modify, and delete operations.
    Validates all paths stay within the repository root (prevents path traversal).
    """
    if root is None:
        root = _repo_root()
    root_resolved = root.resolve()
    for change in changes:
        target = (root / change.path).resolve()
        try:
            target.relative_to(root_resolved)
        except ValueError as err:
            raise ValueError(f"Path '{change.path}' escapes repository root") from err
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
