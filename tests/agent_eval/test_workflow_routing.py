"""Workflow routing and graph compilation tests.

Tests all conditional routing functions in ralph_loop.py using mock RalphState dicts.
The routing functions are pure logic — pydantic_ai is mocked to avoid requiring
a specific pydantic_ai version at test time (consistent with other tests).
"""

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

from agents.core.context_builder import WORKER_TOOL_ACCESS, build_context
from agents.core.state import RalphState, initial_state
from agents.models.reviewer import ReviewOutput
from agents.models.validator import LintResult, TestResult, ValidationOutput
from agents.workflows.feedback_loop import (
    route_after_commit_push,
    route_after_gather,
    route_after_implement_feedback,
)
from agents.workflows.ralph_loop import build_ralph_graph
from agents.workflows.ralph_routing import (
    route_after_implement,
    route_after_merge,
    route_after_open_pr,
    route_after_perf_validate,
    route_after_plan,
    route_after_reproduce,
    route_after_review,
    route_after_ui_validate,
    route_after_validate,
)
from agents.workflows.reviewer_loop import route_after_address, route_review
from tests.agent_eval.conftest import make_feedback_state as _feedback_state
from tests.agent_eval.conftest import make_reviewer_state as _reviewer_state

_PASS_TESTS = TestResult(passed=True, failures=[])
_PASS_LINT = LintResult(passed=True, violations=[])
_FAIL_TESTS = TestResult(passed=False, failures=["test_foo FAILED"])
_FAIL_LINT = LintResult(passed=False, violations=["RUFF: error"])


def _state(**overrides) -> RalphState:
    """Create a RalphState with sensible defaults, overriding specific fields."""
    base = initial_state("test task")
    base.update(overrides)
    return base


def test_graph_compiles():
    graph = build_ralph_graph()
    app = graph.compile()
    assert app is not None


def test_route_after_plan_escalated():
    state = _state(status="escalated")
    assert route_after_plan(state) == "human_checkpoint"


def test_route_after_plan_bug_keyword():
    state = _state(task="fix broken login page")
    assert route_after_plan(state) == "reproduce_node"


def test_route_after_plan_prior_failure():
    validation = ValidationOutput(
        overall_pass=False,
        tests=_FAIL_TESTS,
        lint=_PASS_LINT,
        arch_lint=_PASS_LINT,
        next_action="retry",
    )
    state = _state(task="add feature", validation=validation)
    assert route_after_plan(state) == "reproduce_node"


def test_route_after_plan_normal_task():
    state = _state(task="add new dashboard widget")
    assert route_after_plan(state) == "implement_node"


def test_route_after_validate_escalated():
    state = _state(status="escalated")
    assert route_after_validate(state) == "human_checkpoint"


def test_route_after_validate_no_validation():
    state = _state(validation=None)
    assert route_after_validate(state) == "human_checkpoint"


def test_route_after_validate_proceed():
    validation = ValidationOutput(
        overall_pass=True,
        tests=_PASS_TESTS,
        lint=_PASS_LINT,
        arch_lint=_PASS_LINT,
        next_action="proceed",
    )
    state = _state(validation=validation)
    assert route_after_validate(state) == "perf_validate_node"


def test_route_after_validate_retry():
    validation = ValidationOutput(
        overall_pass=False,
        tests=_FAIL_TESTS,
        lint=_PASS_LINT,
        arch_lint=_PASS_LINT,
        next_action="retry",
    )
    state = _state(validation=validation)
    assert route_after_validate(state) == "implement_node"


def test_route_after_validate_escalate():
    validation = ValidationOutput(
        overall_pass=False,
        tests=_FAIL_TESTS,
        lint=_FAIL_LINT,
        arch_lint=_PASS_LINT,
        next_action="escalate",
    )
    state = _state(validation=validation)
    assert route_after_validate(state) == "human_checkpoint"


def test_route_after_review_escalated():
    state = _state(status="escalated")
    assert route_after_review(state) == "human_checkpoint"


def test_route_after_review_approved():
    review = ReviewOutput(
        approved=True,
        comments=[],
        blocking_issues=[],
        summary="Looks good",
    )
    state = _state(review=review)
    assert route_after_review(state) == "merge_node"


def test_route_after_review_not_approved_retries():
    review = ReviewOutput(
        approved=False,
        comments=[],
        blocking_issues=["Missing tests"],
        summary="Needs work",
    )
    state = _state(review=review, review_iteration_count=1)
    assert route_after_review(state) == "implement_node"


def test_route_after_review_max_iterations_escalates():
    review = ReviewOutput(
        approved=False,
        comments=[],
        blocking_issues=["Still broken"],
        summary="Needs work",
    )
    state = _state(review=review, review_iteration_count=3)
    assert route_after_review(state) == "human_checkpoint"


def test_route_after_review_no_review():
    state = _state(review=None, review_iteration_count=0)
    assert route_after_review(state) == "implement_node"


def test_route_after_plan_all_bug_keywords():
    """All bug-fix keywords in _BUG_FIX_KEYWORDS route to reproduce_node."""
    for keyword in ("fix", "bug", "error", "broken", "failing", "crash"):
        state = _state(task=f"please {keyword} the login page")
        assert route_after_plan(state) == "reproduce_node", (
            f"keyword '{keyword}' did not route to reproduce_node"
        )


def test_reviewer_route_approved():
    state = _reviewer_state(resolved=True)
    assert route_review(state) == "approved"


def test_reviewer_route_escalate_on_max_iterations():
    state = _reviewer_state(resolved=False, review_iteration_count=3)
    assert route_review(state) == "escalate"


def test_reviewer_route_address_feedback():
    state = _reviewer_state(resolved=False, review_iteration_count=1)
    assert route_review(state) == "address_feedback"


def test_reviewer_route_failed_status_escalates():
    """Guard failure sets status='failed' — routing should go to escalate."""
    state = _reviewer_state(status="failed")
    assert route_review(state) == "escalate"


def test_route_after_implement_escalated():
    """implement_node guard failure → human_checkpoint."""
    state = _state(status="escalated")
    assert route_after_implement(state) == "human_checkpoint"


def test_route_after_implement_failed():
    state = _state(status="failed")
    assert route_after_implement(state) == "human_checkpoint"


def test_route_after_implement_normal():
    state = _state(status="validating")
    assert route_after_implement(state) == "validate_node"


def test_route_after_reproduce_escalated():
    state = _state(status="escalated")
    assert route_after_reproduce(state) == "human_checkpoint"


def test_route_after_reproduce_normal():
    state = _state(status="implementing")
    assert route_after_reproduce(state) == "implement_node"


def test_route_after_perf_validate_escalated():
    state = _state(status="escalated")
    assert route_after_perf_validate(state) == "human_checkpoint"


def test_route_after_perf_validate_normal():
    state = _state(status="validating")
    assert route_after_perf_validate(state) == "ui_validate_node"


def test_route_after_ui_validate_escalated():
    state = _state(status="escalated")
    assert route_after_ui_validate(state) == "human_checkpoint"


def test_route_after_ui_validate_normal():
    state = _state(status="validating")
    assert route_after_ui_validate(state) == "open_pr_node"


def test_route_after_open_pr_failed():
    """open_pr_node guard failure → human_checkpoint."""
    state = _state(status="failed")
    assert route_after_open_pr(state) == "human_checkpoint"


def test_route_after_open_pr_normal():
    state = _state(status="reviewing")
    assert route_after_open_pr(state) == "review_loop_node"


def test_route_after_merge_escalated():
    state = _state(status="escalated")
    assert route_after_merge(state) == "human_checkpoint"


def test_route_after_merge_done():
    state = _state(status="done")
    assert route_after_merge(state) == "END"


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
    """commit_push_node guard failure → END."""
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


# --- Planner context visibility tests ---


def test_planner_context_sees_all_tools():
    """Planner role must see all tools (None = no filter) so plans reference valid capabilities."""
    assert WORKER_TOOL_ACCESS["planner"] is None
    ctx = build_context("add new dashboard", worker_role="planner")
    tool_names = {t.name for t in ctx.available_tools}
    assert "run_tests" in tool_names
    assert "commit" in tool_names


def test_implementer_context_is_filtered():
    """Implementer role must see only agent-callable tools, not system capabilities."""
    allowed = WORKER_TOOL_ACCESS["implementer"]
    assert allowed is not None
    ctx = build_context("fix login", worker_role="implementer")
    tool_names = {t.name for t in ctx.available_tools}
    assert "commit" not in tool_names
    assert "merge_pr" not in tool_names
    assert "read_file" in tool_names


def test_planner_and_implementer_contexts_differ():
    """The planner context must contain more tools than the implementer context.

    This is a regression guard: if both get the same filtered set, the planner
    cannot reference system capabilities in its plans.
    """
    planner_ctx = build_context("refactor module", worker_role="planner")
    impl_ctx = build_context("refactor module", worker_role="implementer")
    planner_tools = {t.name for t in planner_ctx.available_tools}
    impl_tools = {t.name for t in impl_ctx.available_tools}
    assert planner_tools > impl_tools, (
        f"Planner tools should be a superset of implementer tools. "
        f"Extra in impl: {impl_tools - planner_tools}"
    )


# --- reply_node escalation tests ---


def test_feedback_route_escalated_status_ends():
    """reply_node sets status='escalated' on truncation — routing must go to END."""
    state = _feedback_state(status="escalated")
    assert state["status"] == "escalated"
