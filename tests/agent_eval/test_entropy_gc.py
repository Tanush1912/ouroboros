"""Agent eval: entropy GC task.

Tests the typed model contracts for the entropy GC system.
Worker functions are mocked — no pydantic_ai or GCP credentials required.
"""

import textwrap
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agents.models.cleaner import CleanupOutput, EntropyViolation

DUPLICATE_LOGGER = textwrap.dedent("""
    import datetime

    def format_timestamp(ts: float) -> str:
        return datetime.datetime.fromtimestamp(ts).isoformat()
""")


@pytest.fixture
def tmp_repo_with_gp001(tmp_path: Path) -> Path:
    """Repo with GP-001 violation: duplicate utility in two packages."""
    for pkg in ["billing", "auth"]:
        pkg_dir = tmp_path / pkg
        pkg_dir.mkdir()
        (pkg_dir / "utils.py").write_text(DUPLICATE_LOGGER)
    (tmp_path / "repo_index").mkdir()
    (tmp_path / "repo_index" / "symbols.json").write_text("{}")
    (tmp_path / "repo_index" / "file_map.json").write_text("{}")
    return tmp_path


def test_gc_detects_gp001_violation(tmp_repo_with_gp001: Path) -> None:
    """Golden lint detects the duplicate utility function as GP-001 violation."""
    from lint.golden_lint import check_gp001_duplicates

    violations = check_gp001_duplicates(tmp_repo_with_gp001)
    gp001_violations = [v for v in violations if "GP-001" in v]
    assert len(gp001_violations) >= 1


def test_entropy_violation_model_is_valid() -> None:
    """EntropyViolation model validates correctly."""
    v = EntropyViolation(
        principle="GP-001",
        file="billing/utils.py",
        description="format_timestamp duplicated in auth/utils.py",
        suggested_fix="Move to shared agents/core/utils.py and update imports",
        auto_fixable=True,
        severity="high",
    )
    assert v.principle == "GP-001"
    assert v.auto_fixable is True
    assert v.severity == "high"


def test_cleanup_output_with_auto_fixable_pr() -> None:
    """CleanupOutput with auto-fixable violation has recommended PR."""
    cleanup = CleanupOutput(
        violations=[
            EntropyViolation(
                principle="GP-001",
                file="billing/utils.py",
                description="format_timestamp duplicated in auth/utils.py",
                suggested_fix="Move to shared module",
                auto_fixable=True,
                severity="high",
            )
        ],
        quality_scores={"billing": 7.0, "auth": 7.0},
        recommended_prs=["[gc] GP-001: remove duplicate format_timestamp utility"],
        human_review_needed=[],
    )

    gp001 = [v for v in cleanup.violations if v.principle == "GP-001"]
    assert len(gp001) >= 1
    assert gp001[0].auto_fixable is True
    assert len(cleanup.recommended_prs) >= 1
    assert cleanup.has_blocking_violations() is True


def test_cleanup_output_non_auto_fixable_goes_to_human() -> None:
    """Non-auto-fixable violations go to human_review_needed."""
    cleanup = CleanupOutput(
        violations=[
            EntropyViolation(
                principle="GP-002",
                file="agents/core/context_builder.py",
                description="File has 520 lines (max 500)",
                suggested_fix="Split into context_builder.py and context_scorer.py",
                auto_fixable=False,
                severity="medium",
            )
        ],
        quality_scores={"agents": 8.0},
        recommended_prs=[],
        human_review_needed=["GP-002: context_builder.py needs manual split — judgment required"],
    )

    assert len(cleanup.human_review_needed) >= 1
    assert len(cleanup.recommended_prs) == 0
    assert not cleanup.has_blocking_violations()


def test_cleanup_output_score_calculation() -> None:
    """CleanupOutput.overall_score() averages domain scores correctly."""
    cleanup = CleanupOutput(
        violations=[],
        quality_scores={"agents": 8.0, "lint": 10.0, "tests": 6.0},
        recommended_prs=[],
        human_review_needed=[],
    )
    assert cleanup.overall_score() == pytest.approx(8.0)


def test_cleanup_output_no_violations_perfect_score() -> None:
    """Empty violations with perfect scores produces 10.0."""
    cleanup = CleanupOutput(
        violations=[],
        quality_scores={"agents": 10.0, "lint": 10.0},
        recommended_prs=[],
        human_review_needed=[],
    )
    assert cleanup.overall_score() == pytest.approx(10.0)
    assert not cleanup.has_blocking_violations()


def test_violation_cluster_by_principle() -> None:
    """Multiple violations of same principle cluster together for one PR."""
    violations = [
        EntropyViolation(
            principle="GP-001",
            file="billing/utils.py",
            description="format_timestamp duplicated",
            suggested_fix="Move to shared module",
            auto_fixable=True,
            severity="high",
        ),
        EntropyViolation(
            principle="GP-001",
            file="auth/utils.py",
            description="format_timestamp duplicated",
            suggested_fix="Move to shared module",
            auto_fixable=True,
            severity="high",
        ),
        EntropyViolation(
            principle="GP-005",
            file="agents/core/guards.py",
            description="print() call detected",
            suggested_fix="Replace with logfire.info()",
            auto_fixable=True,
            severity="low",
        ),
    ]

    clusters: dict[str, list] = {}
    for v in violations:
        if v.auto_fixable:
            clusters.setdefault(v.principle, []).append(v)

    assert len(clusters) == 2
    assert len(clusters["GP-001"]) == 2
    assert len(clusters["GP-005"]) == 1

    @pytest.mark.asyncio
    async def test_cleaner_called_with_mock() -> None:
        """Verify cleaner worker can be mocked for testing."""
        mock_cleanup = CleanupOutput(
            violations=[],
            quality_scores={"agents": 10.0},
            recommended_prs=[],
            human_review_needed=[],
        )

        mock_run_cleaner = AsyncMock(return_value=mock_cleanup)
        with patch.dict(
            "sys.modules", {"agents.workers.cleaner": MagicMock(run_cleaner=mock_run_cleaner)}
        ):
            import sys

            worker_module = sys.modules["agents.workers.cleaner"]
            result = await worker_module.run_cleaner(scan_report="No violations")
            assert result.overall_score() == pytest.approx(10.0)
