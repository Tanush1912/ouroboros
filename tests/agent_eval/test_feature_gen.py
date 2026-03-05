"""Agent eval: feature generation task.

Tests the typed model contracts that agents must satisfy.
Worker functions are mocked — no pydantic_ai or GCP credentials required.
"""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agents.models.implementer import FileChange, ImplementOutput
from agents.models.planner import ExecutionStep, PlanOutput
from agents.models.reviewer import ReviewOutput

FEATURE_TASK = "Add a /health endpoint that returns HTTP 200 with {status: ok}"


def test_plan_output_for_feature_task() -> None:
    """PlanOutput correctly models a feature generation task."""
    plan = PlanOutput(
        task_summary="Add /health endpoint returning 200 {status: ok}",
        steps=[
            ExecutionStep(
                description="Create health endpoint handler",
                files_affected=["api/health.py"],
                tool="fs",
                expected_output="health.py with GET /health handler",
            ),
            ExecutionStep(
                description="Run tests",
                files_affected=[],
                tool="shell",
                expected_output="pytest passes",
            ),
        ],
        test_strategy="pytest tests/test_health.py — assert status_code == 200",
        risk_level="low",
        requires_human_review=False,
        affected_domains=["api"],
    )

    assert plan.risk_level in ("low", "medium")
    assert len(plan.steps) >= 2
    assert any("health" in s.description.lower() for s in plan.steps)
    assert "health" in plan.test_strategy.lower()
    assert "api" in plan.affected_domains


def test_implement_output_creates_health_file() -> None:
    """ImplementOutput models a health endpoint file creation."""
    health_content = '''"""Health endpoint."""
from pydantic import BaseModel

class HealthResult(BaseModel):
    status: str = "ok"

async def health_check():
    return HealthResult()
'''
    impl = ImplementOutput(
        files_changed=[
            FileChange(
                path="api/health.py",
                operation="create",
                content=health_content,
                diff_summary="Created health endpoint module",
            ),
        ],
        commit_message="feat(api): add /health endpoint",
        implementation_notes="Created minimal health check following GP-006 naming",
        test_commands=["pytest tests/test_health.py"],
    )

    created_files = [f for f in impl.files_changed if f.operation == "create"]
    assert len(created_files) >= 1
    assert any("health" in f.path for f in created_files)
    health_file = created_files[0]
    assert health_file.content is not None
    assert any(
        suffix in health_file.content
        for suffix in ("Result", "Schema", "Output")
    )


def test_review_output_approves_clean_implementation() -> None:
    """ReviewOutput models approval of a clean implementation."""
    review = ReviewOutput(
        approved=True,
        comments=[],
        blocking_issues=[],
        summary="Clean implementation. Health endpoint follows GP-006.",
        arch_violations=[],
    )

    assert review.approved
    assert len(review.blocking_issues) == 0
    assert len(review.arch_violations) == 0


def test_review_output_blocks_with_arch_violation() -> None:
    """ReviewOutput correctly models rejection due to architecture violation."""
    from agents.models.reviewer import ReviewComment
    review = ReviewOutput(
        approved=False,
        comments=[
            ReviewComment(
                file="api/health.py",
                line=5,
                severity="blocking",
                comment="Imports from agents.workers.planner — tools cannot import workers (ARCH-002)",
                suggested_fix="Remove the worker import. Use agents.models.planner.PlanOutput instead.",
            )
        ],
        blocking_issues=["ARCH-002: tool imports worker — violates layer dependency rules"],
        summary="Blocking architecture violation detected.",
        arch_violations=["ARCH-002: api/health.py imports from agents.workers.planner"],
    )

    assert not review.approved
    assert len(review.blocking_issues) == 1
    assert any("ARCH" in v for v in review.arch_violations)


@pytest.mark.asyncio
async def test_reviewer_called_with_mock() -> None:
    """Verify reviewer worker can be mocked for testing."""
    mock_review = ReviewOutput(
        approved=True,
        comments=[],
        blocking_issues=[],
        summary="LGTM",
        arch_violations=[],
    )

    mock_run_reviewer = AsyncMock(return_value=mock_review)
    with patch.dict("sys.modules", {"agents.workers.reviewer": MagicMock(run_reviewer=mock_run_reviewer)}):
        import sys
        worker_module = sys.modules["agents.workers.reviewer"]
        result = await worker_module.run_reviewer(pr_number=42, task=FEATURE_TASK)
        assert result.approved
        mock_run_reviewer.assert_called_once_with(pr_number=42, task=FEATURE_TASK)
