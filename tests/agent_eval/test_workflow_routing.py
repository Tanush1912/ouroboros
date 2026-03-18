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

from agents.core.state import RalphState, initial_state
from agents.models.reviewer import ReviewOutput
from agents.models.validator import LintResult, TestResult, ValidationOutput
from agents.workflows.ralph_loop import build_ralph_graph
from agents.workflows.ralph_routing import (
    route_after_implement,
    route_after_merge,
    route_after_mutation,
    route_after_open_pr,
    route_after_perf_validate,
    route_after_plan,
    route_after_reproduce,
    route_after_review,
    route_after_test_writer,
    route_after_ui_validate,
    route_after_validate,
)
from agents.workflows.reviewer_loop import route_review
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
    assert route_after_validate(state) == "mutation_validate_node"


def test_route_after_validate_retry_lint_failure():
    """Lint failures route to implement_node (code needs fixing)."""
    validation = ValidationOutput(
        overall_pass=False,
        tests=_PASS_TESTS,
        lint=_FAIL_LINT,
        arch_lint=_PASS_LINT,
        next_action="retry",
    )
    state = _state(validation=validation)
    assert route_after_validate(state) == "implement_node"


def test_route_after_validate_quality_fail_to_test_writer():
    """Tests pass but quality fails → route to test_writer_node."""
    from agents.models.test_quality import TestQualityResult

    bad_quality = TestQualityResult(
        score=30,
        passed=False,
        assertion_density=0.5,
        trivial_test_count=3,
        edge_case_coverage=0.0,
    )
    validation = ValidationOutput(
        overall_pass=False,
        tests=_PASS_TESTS,
        lint=_PASS_LINT,
        arch_lint=_PASS_LINT,
        next_action="retry",
        test_quality=bad_quality,
    )
    state = _state(validation=validation)
    assert route_after_validate(state) == "test_writer_node"


def test_route_after_validate_test_writer_maxed_escalates():
    """Test writer at max iterations + quality fail → escalate."""
    from agents.models.test_quality import TestQualityResult

    bad_quality = TestQualityResult(
        score=30,
        passed=False,
        assertion_density=0.5,
        trivial_test_count=3,
        edge_case_coverage=0.0,
    )
    validation = ValidationOutput(
        overall_pass=False,
        tests=_PASS_TESTS,
        lint=_PASS_LINT,
        arch_lint=_PASS_LINT,
        next_action="retry",
        test_quality=bad_quality,
    )
    state = _state(validation=validation, test_writer_iteration=3)
    assert route_after_validate(state) == "human_checkpoint"


def test_route_after_validate_test_file_failure_to_test_writer():
    """Test failures in test files route to test_writer, not implementer."""
    fail_in_test = TestResult(
        passed=False,
        failures=["FAILED tests/test_paths.py::test_repo_root - AssertionError"],
    )
    validation = ValidationOutput(
        overall_pass=False,
        tests=fail_in_test,
        lint=_PASS_LINT,
        arch_lint=_PASS_LINT,
        next_action="retry",
    )
    state = _state(validation=validation)
    assert route_after_validate(state) == "test_writer_node"


def test_route_after_validate_prod_failure_to_implementer():
    """Non-test failures still route to implementer."""
    fail_in_prod = TestResult(
        passed=False,
        failures=["ModuleNotFoundError: No module named 'agents.core.missing'"],
    )
    validation = ValidationOutput(
        overall_pass=False,
        tests=fail_in_prod,
        lint=_PASS_LINT,
        arch_lint=_PASS_LINT,
        next_action="retry",
    )
    state = _state(validation=validation)
    # Non-test failures don't match _test_failures_in_test_files → implementer
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


def test_route_after_review_meaningless_tests_blocks_merge():
    """has_meaningful_tests=False blocks merge even if approved=True."""
    review = ReviewOutput(
        approved=True,
        comments=[],
        blocking_issues=[],
        summary="Code looks fine but tests are meaningless",
        has_meaningful_tests=False,
        test_quality_concerns=["Tests only check 'is not None'"],
    )
    state = _state(review=review, review_iteration_count=1)
    assert route_after_review(state) == "implement_node"


def test_route_after_review_meaningless_tests_escalates_at_max():
    """has_meaningful_tests=False escalates when at max review iterations."""
    review = ReviewOutput(
        approved=True,
        comments=[],
        blocking_issues=[],
        summary="Tests still meaningless",
        has_meaningful_tests=False,
    )
    state = _state(review=review, review_iteration_count=3)
    assert route_after_review(state) == "human_checkpoint"


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
    """implement_node routes to test_writer_node when requires_tests=True."""
    state = _state(status="validating")
    assert route_after_implement(state) == "test_writer_node"


def test_route_after_implement_skips_test_writer():
    """implement_node skips test_writer when plan.requires_tests=False."""
    from agents.models.planner import PlanOutput

    plan = PlanOutput(
        task_summary="Add docstring",
        steps=[],
        test_strategy="Lint only",
        risk_level="low",
        requires_human_review=False,
        requires_tests=False,
    )
    state = _state(status="validating", plan=plan)
    assert route_after_implement(state) == "validate_node"


def test_route_after_implement_runs_test_writer_by_default():
    """implement_node routes to test_writer when plan.requires_tests=True."""
    from agents.models.planner import PlanOutput

    plan = PlanOutput(
        task_summary="Add new endpoint",
        steps=[],
        test_strategy="Unit + integration tests",
        risk_level="medium",
        requires_human_review=False,
        requires_tests=True,
    )
    state = _state(status="validating", plan=plan)
    assert route_after_implement(state) == "test_writer_node"


def test_route_after_test_writer_normal():
    state = _state(status="validating")
    assert route_after_test_writer(state) == "validate_node"


def test_route_after_test_writer_escalated():
    state = _state(status="escalated")
    assert route_after_test_writer(state) == "human_checkpoint"


def test_route_after_reproduce_escalated():
    state = _state(status="escalated")
    assert route_after_reproduce(state) == "human_checkpoint"


def test_route_after_reproduce_normal():
    state = _state(status="implementing")
    assert route_after_reproduce(state) == "implement_node"


def test_route_after_mutation_proceeds():
    """Good kill rate → proceed to perf_validate_node."""
    from agents.models.mutation import MutationSamplingResult

    result = MutationSamplingResult(
        total_mutants=10, killed=8, survived=2, kill_rate=0.8, passed=True
    )
    state = _state(mutation_result=result)
    assert route_after_mutation(state) == "perf_validate_node"


def test_route_after_mutation_low_kill_rate():
    """Low kill rate → route to test_writer for better tests."""
    from agents.models.mutation import MutationSamplingResult

    result = MutationSamplingResult(
        total_mutants=10, killed=3, survived=7, kill_rate=0.3, passed=False
    )
    state = _state(mutation_result=result)
    assert route_after_mutation(state) == "test_writer_node"


def test_route_after_mutation_escalates_at_max():
    """Low kill rate + test writer maxed → escalate."""
    from agents.models.mutation import MutationSamplingResult

    result = MutationSamplingResult(
        total_mutants=10, killed=3, survived=7, kill_rate=0.3, passed=False
    )
    state = _state(mutation_result=result, test_writer_iteration=3)
    assert route_after_mutation(state) == "human_checkpoint"


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


# Feedback loop, reviewer loop, and context tests moved to test_feedback_routing.py (GP-002)
