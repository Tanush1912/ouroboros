"""Agent eval: bug fix task.

Tests the typed model contracts that agents must satisfy.
Worker functions are mocked — no pydantic_ai or GCP credentials required.
Integration tests (with real agents) require: pip install pydantic-ai google-cloud-aiplatform
"""

import textwrap
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agents.models.implementer import FileChange, ImplementOutput
from agents.models.planner import ExecutionStep, PlanOutput
from agents.models.validator import LintResult, TestResult, ValidationOutput

BUGGY_COUNTER_CODE = textwrap.dedent("""
    def count_items(items: list) -> int:
        \"\"\"Return the count of items.\"\"\"
        count = 0
        for i in range(len(items) - 1):  # BUG: off by one
            count += 1
        return count
""")

FIXED_COUNTER_CODE = textwrap.dedent("""
    def count_items(items: list) -> int:
        \"\"\"Return the count of items.\"\"\"
        count = 0
        for i in range(len(items)):
            count += 1
        return count
""")


@pytest.fixture
def tmp_repo(tmp_path: Path) -> Path:
    (tmp_path / "utils").mkdir()
    (tmp_path / "utils" / "counter.py").write_text(BUGGY_COUNTER_CODE)
    (tmp_path / "repo_index").mkdir()
    (tmp_path / "repo_index" / "symbols.json").write_text("{}")
    (tmp_path / "repo_index" / "file_map.json").write_text("{}")
    return tmp_path


def test_plan_output_model_is_valid() -> None:
    """PlanOutput can be constructed and validated."""
    plan = PlanOutput(
        task_summary="Fix off-by-one error in count_items",
        steps=[
            ExecutionStep(
                description="Fix range(len(items) - 1) to range(len(items))",
                files_affected=["utils/counter.py"],
                tool="fs",
                expected_output="Fixed file written",
            ),
        ],
        test_strategy="Run pytest — count_items([1,2,3]) should return 3",
        risk_level="low",
        requires_human_review=False,
    )
    assert plan.risk_level == "low"
    assert not plan.requires_human_review
    assert len(plan.steps) == 1
    assert plan.steps[0].tool == "fs"


def test_implement_output_contains_fix() -> None:
    """ImplementOutput model validates a file change correctly."""
    impl = ImplementOutput(
        files_changed=[
            FileChange(
                path="utils/counter.py",
                operation="modify",
                content=FIXED_COUNTER_CODE,
                diff_summary="Fixed off-by-one",
            )
        ],
        commit_message="fix(utils): correct off-by-one in count_items",
        implementation_notes="Changed range(len(items) - 1) to range(len(items))",
        test_commands=["pytest utils/"],
    )
    assert len(impl.files_changed) == 1
    assert impl.files_changed[0].operation == "modify"
    assert impl.files_changed[0].content is not None
    assert "range(len(items))" in impl.files_changed[0].content
    assert "- 1" not in impl.files_changed[0].content


def test_validation_output_next_action_proceed() -> None:
    """ValidationOutput.next_action == 'proceed' when all checks pass."""
    validation = ValidationOutput(
        tests=TestResult(passed=True, failures=[], coverage=100.0),
        lint=LintResult(passed=True, violations=[]),
        arch_lint=LintResult(passed=True, violations=[]),
        overall_pass=True,
        next_action="proceed",
    )
    assert validation.overall_pass
    assert validation.next_action == "proceed"


def test_validation_output_next_action_retry_on_test_fail() -> None:
    """ValidationOutput.next_action == 'retry' when tests fail (fixable)."""
    validation = ValidationOutput(
        tests=TestResult(
            passed=False,
            failures=["FAILED utils/test_counter.py::test_count - AssertionError: 2 != 3"],
        ),
        lint=LintResult(passed=True, violations=[]),
        arch_lint=LintResult(passed=True, violations=[]),
        overall_pass=False,
        next_action="retry",
        failure_summary="Off-by-one test failure — still needs fix",
    )
    assert not validation.overall_pass
    assert validation.next_action == "retry"
    assert len(validation.tests.failures) == 1


@pytest.mark.asyncio
async def test_planner_called_with_mock() -> None:
    """Verify planner worker can be mocked for testing."""
    mock_plan = PlanOutput(
        task_summary="Fix off-by-one",
        steps=[],
        test_strategy="pytest",
        risk_level="low",
        requires_human_review=False,
    )

    mock_run_planner = AsyncMock(return_value=mock_plan)
    with patch.dict(
        "sys.modules", {"agents.workers.planner": MagicMock(run_planner=mock_run_planner)}
    ):
        import sys

        worker_module = sys.modules["agents.workers.planner"]
        result = await worker_module.run_planner("Fix the off-by-one error")
        assert result.risk_level == "low"
        mock_run_planner.assert_called_once()
