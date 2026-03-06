"""Workflow routing and graph compilation tests.

Tests all conditional routing functions in ralph_loop.py using mock RalphState dicts.
The routing functions are pure logic — pydantic_ai is mocked to avoid requiring
a specific pydantic_ai version at test time (consistent with other tests).
"""

import sys
import types
from unittest.mock import MagicMock

# Mock pydantic_ai so the full import chain (ralph_loop → workers → tools → pydantic_ai)
# works without a specific pydantic_ai version installed.
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

from agents.core.state import RalphState, initial_state
from agents.models.reviewer import ReviewOutput
from agents.models.validator import LintResult, TestResult, ValidationOutput
from agents.workflows.ralph_loop import (
    build_ralph_graph,
    route_after_plan,
    route_after_review,
    route_after_validate,
)

_PASS_TESTS = TestResult(passed=True, failures=[])
_PASS_LINT = LintResult(passed=True, violations=[])
_FAIL_TESTS = TestResult(passed=False, failures=["test_foo FAILED"])
_FAIL_LINT = LintResult(passed=False, violations=["RUFF: error"])


def _state(**overrides) -> RalphState:
    """Create a RalphState with sensible defaults, overriding specific fields."""
    base = initial_state("test task")
    base.update(overrides)
    return base


# --- build_ralph_graph ---


def test_graph_compiles():
    graph = build_ralph_graph()
    app = graph.compile()
    assert app is not None


# --- route_after_plan ---


def test_route_after_plan_escalated():
    state = _state(status="escalated")
    assert route_after_plan(state) == "implement_node"


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


# --- route_after_validate ---


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


# --- route_after_review ---


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
