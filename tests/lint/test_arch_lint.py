"""Tests for architecture lint rules."""

from pathlib import Path

from lint.arch_lint import check_file, run_arch_lint
from tests.lint.helpers import write_py


def test_worker_cross_import_detected(tmp_path: Path) -> None:
    write_py(
        tmp_path,
        "agents/workers/planner.py",
        """
        from agents.workers.reviewer import ReviewerWorker
        class PlannerWorker: pass
    """,
    )
    violations = check_file(tmp_path / "agents/workers/planner.py", tmp_path)
    assert any("ARCH-VIOLATION" in v and "workers" in v for v in violations)


def test_tool_imports_worker_detected(tmp_path: Path) -> None:
    write_py(
        tmp_path,
        "agents/tools/fs.py",
        """
        from agents.workers.planner import run_planner
        def read_file(path: str) -> str: ...
    """,
    )
    violations = check_file(tmp_path / "agents/tools/fs.py", tmp_path)
    assert any("ARCH-VIOLATION" in v for v in violations)


def test_clean_file_no_violations(tmp_path: Path) -> None:
    write_py(
        tmp_path,
        "agents/workers/planner.py",
        """
        from agents.models.planner import PlanOutput
        from agents.core.context_builder import build_context
        class PlannerWorker: pass
    """,
    )
    violations = check_file(tmp_path / "agents/workers/planner.py", tmp_path)
    assert violations == []


def test_remediation_message_in_violation(tmp_path: Path) -> None:
    write_py(
        tmp_path,
        "agents/workers/planner.py",
        """
        from agents.workers.reviewer import run_reviewer
    """,
    )
    violations = check_file(tmp_path / "agents/workers/planner.py", tmp_path)
    assert any("REMEDIATION" in v for v in violations)


def test_run_arch_lint_on_clean_dir(tmp_path: Path) -> None:
    write_py(
        tmp_path,
        "agents/models/planner.py",
        """
        from pydantic import BaseModel
        class PlanOutput(BaseModel): pass
    """,
    )
    violations = run_arch_lint(".", tmp_path)
    assert violations == []
