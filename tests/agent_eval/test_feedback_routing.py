"""Tests for feedback loop, reviewer loop, and context visibility routing."""

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

from agents.core.context_builder import WORKER_TOOL_ACCESS, build_context
from agents.workflows.feedback_loop import (
    route_after_commit_push,
    route_after_gather,
    route_after_implement_feedback,
)
from agents.workflows.reviewer_loop import route_after_address
from tests.agent_eval.conftest import make_feedback_state as _feedback_state
from tests.agent_eval.conftest import make_reviewer_state as _reviewer_state


def test_feedback_route_after_gather_failed():
    state = _feedback_state(status="failed")
    assert route_after_gather(state) == "END"


def test_feedback_route_after_gather_normal():
    state = _feedback_state(status="implementing")
    assert route_after_gather(state) == "implement_feedback_node"


def test_feedback_route_after_implement_failed():
    state = _feedback_state(status="failed")
    assert route_after_implement_feedback(state) == "END"


def test_feedback_route_after_implement_normal():
    state = _feedback_state(status="validating")
    assert route_after_implement_feedback(state) == "validate_feedback_node"


def test_feedback_route_after_commit_push_failed():
    state = _feedback_state(status="failed")
    assert route_after_commit_push(state) == "END"


def test_feedback_route_after_commit_push_normal():
    state = _feedback_state(status="replying")
    assert route_after_commit_push(state) == "reply_node"


def test_reviewer_route_after_address_failed():
    state = _reviewer_state(status="failed")
    assert route_after_address(state) == "END"


def test_reviewer_route_after_address_normal():
    state = _reviewer_state(status="reviewing")
    assert route_after_address(state) == "review_node"


def test_planner_context_sees_all_tools():
    assert WORKER_TOOL_ACCESS["planner"] is None
    ctx = build_context("add new dashboard", worker_role="planner")
    tool_names = {t.name for t in ctx.available_tools}
    assert "run_tests" in tool_names
    assert "commit" in tool_names


def test_implementer_context_is_filtered():
    allowed = WORKER_TOOL_ACCESS["implementer"]
    assert allowed is not None
    ctx = build_context("fix login", worker_role="implementer")
    tool_names = {t.name for t in ctx.available_tools}
    assert "commit" not in tool_names
    assert "read_file" in tool_names


def test_planner_and_implementer_contexts_differ():
    planner_ctx = build_context("refactor module", worker_role="planner")
    impl_ctx = build_context("refactor module", worker_role="implementer")
    planner_tools = {t.name for t in planner_ctx.available_tools}
    impl_tools = {t.name for t in impl_ctx.available_tools}
    assert planner_tools > impl_tools


def test_feedback_route_escalated_status_ends():
    state = _feedback_state(status="escalated")
    assert state["status"] == "escalated"
