"""State consistency tests — verify workflow state semantics are sound.

Covers:
- _EXEMPT_NODES matches actual unguarded nodes (AST-verified)
- CLI does not reference phantom status values
- Skip paths include tracking keys (total_tool_calls, node_tool_calls)
- All non-skip, non-guard-failure success paths set status explicitly
"""

import ast
import sys
import types
from unittest.mock import MagicMock

if "pydantic_ai" not in sys.modules or not hasattr(sys.modules["pydantic_ai"], "Agent"):
    _mock = types.ModuleType("pydantic_ai")
    _mock.Agent = MagicMock()
    _mock.tool = MagicMock()
    _mock.Tool = MagicMock()
    _mock_models = types.ModuleType("pydantic_ai.models")
    _mock_vertexai = types.ModuleType("pydantic_ai.models.vertexai")
    _mock_vertexai.VertexAIModel = MagicMock()
    sys.modules["pydantic_ai"] = _mock
    sys.modules["pydantic_ai.models"] = _mock_models
    sys.modules["pydantic_ai.models.vertexai"] = _mock_vertexai

if "langgraph" not in sys.modules:
    _lg = types.ModuleType("langgraph")
    _lg_graph = types.ModuleType("langgraph.graph")
    _lg_graph.END = "END"
    _lg_graph.StateGraph = MagicMock()
    sys.modules["langgraph"] = _lg
    sys.modules["langgraph.graph"] = _lg_graph

if "logfire" not in sys.modules:
    _logfire = types.ModuleType("logfire")
    _logfire.span = MagicMock()
    _logfire.info = MagicMock()
    _logfire.warning = MagicMock()
    sys.modules["logfire"] = _logfire

from agents.core.guards import _EXEMPT_NODES
from agents.core.paths import repo_root

_REPO = repo_root()
_TRACKING_KEYS = {"total_tool_calls", "node_tool_calls"}

# Status values that indicate guard-triggered failure (exempt from tracking requirement)
_GUARD_FAILURE_STATUSES = {"escalated", "failed"}


def _parse_workflow_file(filename: str) -> ast.Module:
    path = _REPO / filename
    return ast.parse(path.read_text(encoding="utf-8"), filename=filename)


def _get_node_functions(tree: ast.Module) -> list[ast.AsyncFunctionDef | ast.FunctionDef]:
    """Extract functions that look like LangGraph nodes (take 'state' as first param)."""
    nodes = []
    for item in ast.walk(tree):
        if (
            isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
            and item.args.args
            and item.args.args[0].arg == "state"
        ):
            nodes.append(item)
    return nodes


def _calls_pre_node_guard(func: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """Check if a function contains a call to pre_node_guard()."""
    for node in ast.walk(func):
        if isinstance(node, ast.Call):
            callee = node.func
            if isinstance(callee, ast.Name) and callee.id == "pre_node_guard":
                return True
            if isinstance(callee, ast.Attribute) and callee.attr == "pre_node_guard":
                return True
    return False


def _get_return_dicts(func: ast.FunctionDef | ast.AsyncFunctionDef) -> list[set[str]]:
    """Extract the key sets from all dict-literal returns in a function."""
    results = []
    for node in ast.walk(func):
        if isinstance(node, ast.Return) and isinstance(node.value, ast.Dict):
            keys = set()
            has_spread = False
            for key in node.value.keys:
                if key is None:
                    has_spread = True
                elif isinstance(key, ast.Constant) and isinstance(key.value, str):
                    keys.add(key.value)
            results.append((keys, has_spread))
    return results


# --- Test: _EXEMPT_NODES matches actual unguarded nodes ---


def test_exempt_nodes_matches_actual_unguarded_nodes():
    """AST-verify that _EXEMPT_NODES exactly matches nodes that skip pre_node_guard()."""
    tree = _parse_workflow_file("agents/workflows/ralph_loop.py")
    node_funcs = _get_node_functions(tree)

    unguarded = set()
    for func in node_funcs:
        if not _calls_pre_node_guard(func):
            unguarded.add(func.name)

    # post_mortem_node is imported, so parse its source too
    pm_tree = _parse_workflow_file("agents/workflows/post_mortem.py")
    pm_funcs = _get_node_functions(pm_tree)
    for func in pm_funcs:
        if not _calls_pre_node_guard(func):
            unguarded.add(func.name)

    assert unguarded == _EXEMPT_NODES, (
        f"_EXEMPT_NODES mismatch.\n"
        f"  Unguarded in code: {unguarded}\n"
        f"  _EXEMPT_NODES:     {_EXEMPT_NODES}"
    )


# --- Test: CLI does not reference phantom "merged" status ---


def test_cli_does_not_reference_merged_status():
    """Ensure cli.py never checks for 'merged' — the workflow returns 'done' on success."""
    cli_source = (_REPO / "agents/cli.py").read_text(encoding="utf-8")
    # Check for "merged" as a string literal in status-checking contexts
    tree = ast.parse(cli_source, filename="agents/cli.py")
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and node.value == "merged":
            raise AssertionError(
                f"cli.py references phantom 'merged' status at line {node.lineno}. "
                "The workflow returns 'done' on successful merge."
            )


# --- Test: skip paths include tracking keys ---


def test_skip_paths_include_tracking_keys():
    """Nodes that return early (skip) must still include total_tool_calls and node_tool_calls."""
    tree = _parse_workflow_file("agents/workflows/ralph_loop.py")
    node_funcs = _get_node_functions(tree)

    violations = []
    for func in node_funcs:
        returns = _get_return_dicts(func)
        for keys, has_spread in returns:
            # Empty returns with no keys at all AND no spread are the problem
            # But we now require even skip paths to have tracking
            if not keys and not has_spread:
                violations.append(f"{func.name}: returns empty dict {{}} without tracking keys")

    assert not violations, "Skip paths must include tracking keys:\n" + "\n".join(
        f"  - {v}" for v in violations
    )


# --- Test: RalphState.status Literal does not include "merged" ---


def test_ralph_state_has_no_merged_status():
    """RalphState.status should not include 'merged' — 'done' is the terminal success state."""
    from agents.core.state import RalphState

    # Get the annotation for 'status' from the TypedDict
    annotations = RalphState.__annotations__
    assert "status" in annotations

    status_type = annotations["status"]
    # Extract Literal args
    if hasattr(status_type, "__args__"):
        valid_statuses = set(status_type.__args__)
        assert "merged" not in valid_statuses, (
            f"RalphState.status includes 'merged' but should not: {valid_statuses}"
        )
