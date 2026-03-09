"""Contract tests: tool registry is populated and build_context() sees tools.

Verifies that REGISTRY is populated at import time (no side-effect imports needed),
build_context() returns a non-empty tool list in a fresh process, and worker agents
wire their tools from the catalog via resolve_worker_tools() (not hardcoded lists).
"""

from pathlib import Path

from agents.core.context_builder import WORKER_TOOL_ACCESS
from agents.models.registry import REGISTRY


def test_registry_populated_at_import():
    """REGISTRY must be non-empty from agents.models.registry import alone."""
    tools = REGISTRY.all_tools()
    assert len(tools) > 0, "REGISTRY.all_tools() is empty — registrations did not fire"


def test_registry_has_core_tools():
    """Spot-check that essential tools are registered."""
    names = REGISTRY.tool_names()
    for expected in ("read_file", "write_file", "run_tests", "commit"):
        assert expected in names, f"Expected tool '{expected}' not found in registry"


def test_registry_tools_have_required_fields():
    """Every registered tool must have non-empty name, description, and category."""
    for tool in REGISTRY.all_tools():
        assert tool.name, f"Tool has empty name: {tool}"
        assert tool.description, f"Tool {tool.name} has empty description"
        assert tool.category, f"Tool {tool.name} has empty category"


def test_build_context_returns_tools():
    """build_context() must return non-empty available_tools without manual imports."""
    from agents.core.context_builder import build_context

    ctx = build_context("test task for registry verification")
    assert len(ctx.available_tools) > 0, (
        "build_context() returned empty available_tools — "
        "REGISTRY was not populated when context_builder imported it"
    )


def test_agent_callable_tools_match_worker_tools():
    """Agent-callable tools in REGISTRY must match planner/implementer tool sets."""
    agent_tools = REGISTRY.agent_callable_tools()
    agent_names = {t.name for t in agent_tools}
    expected = {"read_file", "list_dir", "search_repo", "search_symbol"}
    assert agent_names == expected, (
        f"agent_callable tools {agent_names} don't match worker tool sets {expected}"
    )


def test_context_distinguishes_callable_vs_system_tools():
    """build_context prompt must separate agent-callable from system tools."""
    from agents.core.context_builder import build_context

    ctx = build_context("test task")
    agent_tools = [t for t in ctx.available_tools if t.agent_callable]
    system_tools = [t for t in ctx.available_tools if not t.agent_callable]
    assert len(agent_tools) == 4
    assert len(system_tools) > 0
    prompt = ctx.to_prompt_text()
    assert "Your Tools (you can call these directly)" in prompt
    assert "System Capabilities" in prompt


def test_build_context_worker_role_filters_tools():
    """build_context(worker_role='implementer') returns only implementer's tools."""
    from agents.core.context_builder import build_context

    ctx = build_context("test task", worker_role="implementer")
    tool_names = {t.name for t in ctx.available_tools}
    expected = set(WORKER_TOOL_ACCESS["implementer"])
    assert tool_names == expected, (
        f"worker_role='implementer' returned {tool_names}, expected {expected}"
    )


def test_build_context_no_role_returns_all_tools():
    """build_context() without worker_role returns all registered tools."""
    from agents.core.context_builder import build_context

    ctx = build_context("test task")
    assert len(ctx.available_tools) == len(REGISTRY.all_tools())


def test_build_context_invalid_role_raises():
    """build_context() with invalid worker_role raises KeyError, not silent empty."""
    import pytest

    from agents.core.context_builder import build_context

    with pytest.raises(KeyError, match="Unknown worker_role"):
        build_context("test task", worker_role="nonexistent")


def test_worker_tool_access_derived_from_agent_callable():
    """WORKER_TOOL_ACCESS implementer must be derived from agent_callable, not hand-maintained."""
    from agents.models.tool_catalog import ALL_TOOL_CAPABILITIES

    derived = [t.name for t in ALL_TOOL_CAPABILITIES if t.agent_callable]
    assert WORKER_TOOL_ACCESS["implementer"] == derived
    assert WORKER_TOOL_ACCESS["planner"] is None


def test_worker_tool_access_names_exist_in_registry():
    """Every tool name in WORKER_TOOL_ACCESS must exist in REGISTRY."""
    registry_names = set(REGISTRY.tool_names())
    for role, names in WORKER_TOOL_ACCESS.items():
        if names is None:
            continue  
        for name in names:
            assert name in registry_names, (
                f"WORKER_TOOL_ACCESS['{role}'] references '{name}' which is not in REGISTRY"
            )


def test_resolve_module_covers_all_worker_tool_names():
    """agents/tools/tool_wiring.py _NAME_TO_CALLABLE must map every agent-callable tool."""
    import ast

    src = (Path(__file__).parent.parent.parent / "agents" / "tools" / "tool_wiring.py").read_text(
        encoding="utf-8"
    )
    tree = ast.parse(src)

    mapped_names: set[str] = set()
    for node in ast.walk(tree):
        target = None
        value = None
        if isinstance(node, ast.Assign) and node.targets:
            target = node.targets[0]
            value = node.value
        elif isinstance(node, ast.AnnAssign):
            target = node.target
            value = node.value
        if (
            isinstance(target, ast.Name)
            and target.id == "_NAME_TO_CALLABLE"
            and isinstance(value, ast.Dict)
        ):
            for key in value.keys:
                if isinstance(key, ast.Constant) and isinstance(key.value, str):
                    mapped_names.add(key.value)

    all_needed = set()
    for _role, names in WORKER_TOOL_ACCESS.items():
        if names is not None:
            all_needed.update(names)

    missing = all_needed - mapped_names
    assert not missing, (
        f"_NAME_TO_CALLABLE in tool_wiring.py is missing mappings for: {missing}. "
        f"These names are in WORKER_TOOL_ACCESS but have no callable."
    )


def test_planner_agent_tools_match_catalog():
    """Planner _get_agent() must wire tools from resolve_worker_tools, not a hardcoded list."""
    import ast

    src = (Path(__file__).parent.parent.parent / "agents" / "workers" / "planner.py").read_text(
        encoding="utf-8"
    )
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and any(kw.arg == "tools" for kw in node.keywords):
            tools_kw = next(kw for kw in node.keywords if kw.arg == "tools")
            source_fragment = ast.unparse(tools_kw.value)
            assert "resolve_worker_tools" in source_fragment, (
                f"planner _get_agent() tools= is '{source_fragment}', "
                f"expected a call to resolve_worker_tools()"
            )
            assert '"planner"' in source_fragment or "'planner'" in source_fragment, (
                f"planner _get_agent() must call resolve_worker_tools('planner'), "
                f"got: {source_fragment}"
            )
            break
    else:
        raise AssertionError("No Agent() call with tools= found in planner.py")


def test_implementer_agent_tools_match_catalog():
    """Implementer _get_agent() must wire tools from resolve_worker_tools, not a hardcoded list."""
    import ast

    src = (Path(__file__).parent.parent.parent / "agents" / "workers" / "implementer.py").read_text(
        encoding="utf-8"
    )
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and any(kw.arg == "tools" for kw in node.keywords):
            tools_kw = next(kw for kw in node.keywords if kw.arg == "tools")
            source_fragment = ast.unparse(tools_kw.value)
            assert "resolve_worker_tools" in source_fragment, (
                f"implementer _get_agent() tools= is '{source_fragment}', "
                f"expected a call to resolve_worker_tools()"
            )
            assert '"implementer"' in source_fragment or "'implementer'" in source_fragment, (
                f"implementer _get_agent() must call resolve_worker_tools('implementer'), "
                f"got: {source_fragment}"
            )
            break
    else:
        raise AssertionError("No Agent() call with tools= found in implementer.py")


def test_planner_context_sees_all_tools():
    """build_context(worker_role='planner') returns ALL registered tools."""
    from agents.core.context_builder import build_context

    ctx = build_context("test task", worker_role="planner")
    assert len(ctx.available_tools) == len(REGISTRY.all_tools()), (
        f"Planner should see all {len(REGISTRY.all_tools())} tools, "
        f"but got {len(ctx.available_tools)}"
    )
