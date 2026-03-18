"""Tests for the adaptive pipeline — skip_stages, _resolve_next_stage, _should_skip."""

import sys
import types
from unittest.mock import MagicMock

if "pydantic_ai" not in sys.modules or not hasattr(sys.modules["pydantic_ai"], "Agent"):
    _mock = types.ModuleType("pydantic_ai")
    _mock.Agent = MagicMock()
    _mock.tool = MagicMock()
    _mock.Tool = MagicMock()
    _mock_models = types.ModuleType("pydantic_ai.models")
    _mock_google = types.ModuleType("pydantic_ai.models.google")
    _mock_google.GoogleModel = MagicMock()
    sys.modules["pydantic_ai"] = _mock
    sys.modules["pydantic_ai.models"] = _mock_models
    sys.modules["pydantic_ai.models.google"] = _mock_google

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

from agents.core.state import initial_state
from agents.models.planner import PlanOutput
from agents.workflows.ralph_routing import (
    _resolve_next_stage,
    _should_skip,
    route_after_implement,
)


def _state(**overrides):
    base = initial_state("test task")
    base.update(overrides)
    return base


def _plan(**overrides) -> PlanOutput:
    defaults = {
        "task_summary": "test",
        "steps": [],
        "test_strategy": "test",
        "risk_level": "low",
        "requires_human_review": False,
    }
    defaults.update(overrides)
    return PlanOutput(**defaults)


# --- _resolve_next_stage ---


def test_resolve_next_stage_no_skips():
    state = _state()
    assert _resolve_next_stage(state, "validate") == "mutation_validate_node"


def test_resolve_next_stage_skip_mutation():
    state = _state(plan=_plan(skip_stages=["mutation"]))
    assert _resolve_next_stage(state, "validate") == "perf_validate_node"


def test_resolve_next_stage_skip_chain():
    state = _state(plan=_plan(skip_stages=["mutation", "perf_validate", "ui_validate"]))
    assert _resolve_next_stage(state, "validate") == "open_pr_node"


def test_resolve_next_stage_skip_review():
    state = _state(plan=_plan(skip_stages=["review"]))
    assert _resolve_next_stage(state, "open_pr") == "merge_node"


def test_resolve_next_stage_skip_all_post_validate():
    state = _state(plan=_plan(skip_stages=["mutation", "perf_validate", "ui_validate", "review"]))
    # validate → skip mutation, perf, ui → open_pr (not skippable) → merge
    assert _resolve_next_stage(state, "validate") == "open_pr_node"


# --- _should_skip ---


def test_should_skip_with_stage_in_list():
    state = _state(plan=_plan(skip_stages=["test_writer", "mutation"]))
    assert _should_skip(state, "test_writer")
    assert _should_skip(state, "mutation")
    assert not _should_skip(state, "review")


def test_should_skip_no_plan():
    state = _state()
    assert not _should_skip(state, "test_writer")


def test_should_skip_empty_list():
    state = _state(plan=_plan(skip_stages=[]))
    assert not _should_skip(state, "test_writer")


# --- route_after_implement with skip_stages ---


def test_implement_skips_test_writer_via_skip_stages():
    state = _state(status="validating", plan=_plan(skip_stages=["test_writer"]))
    assert route_after_implement(state) == "validate_node"


def test_implement_runs_test_writer_when_not_skipped():
    state = _state(status="validating", plan=_plan(skip_stages=[]))
    assert route_after_implement(state) == "test_writer_node"
