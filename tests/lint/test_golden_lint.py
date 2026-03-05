"""Tests for golden principle lint rules."""

import textwrap
from pathlib import Path

import pytest

from lint.golden_lint import (
    check_gp001_duplicates,
    check_gp002_file_size,
    check_gp005_no_print,
)


def write_py(tmp_path: Path, rel_path: str, content: str) -> Path:
    target = tmp_path / rel_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(textwrap.dedent(content))
    return target


def test_gp002_file_exceeds_500_lines(tmp_path: Path) -> None:
    content = "\n".join(f"x_{i} = {i}" for i in range(510))
    write_py(tmp_path, "agents/core/big_file.py", content)
    violations = check_gp002_file_size(tmp_path)
    assert any("GP-002" in v and "big_file.py" in v for v in violations)


def test_gp002_file_under_limit_passes(tmp_path: Path) -> None:
    content = "\n".join(f"x_{i} = {i}" for i in range(100))
    write_py(tmp_path, "agents/core/small_file.py", content)
    violations = check_gp002_file_size(tmp_path)
    assert violations == []


def test_gp005_print_detected_outside_scripts(tmp_path: Path) -> None:
    write_py(tmp_path, "agents/workers/planner.py", """
        def run():
            print("hello")
    """)
    violations = check_gp005_no_print(tmp_path)
    assert any("GP-005" in v and "planner.py" in v for v in violations)


def test_gp005_print_allowed_in_scripts(tmp_path: Path) -> None:
    write_py(tmp_path, "scripts/setup.py", """
        def main():
            print("Setting up...")
    """)
    violations = check_gp005_no_print(tmp_path)
    assert not any("scripts" in v for v in violations)


def test_gp001_duplicate_function_detected(tmp_path: Path) -> None:
    body = """
        def format_timestamp(ts: float) -> str:
            import datetime
            return datetime.datetime.fromtimestamp(ts).isoformat()
    """
    write_py(tmp_path, "agents/core/utils.py", body)
    write_py(tmp_path, "agents/tools/helpers.py", body)
    violations = check_gp001_duplicates(tmp_path)
    assert any("GP-001" in v for v in violations)


def test_gp001_unique_functions_pass(tmp_path: Path) -> None:
    write_py(tmp_path, "agents/core/utils.py", """
        def compute_hash(s: str) -> str:
            import hashlib
            return hashlib.sha256(s.encode()).hexdigest()
    """)
    write_py(tmp_path, "agents/tools/helpers.py", """
        def slugify(s: str) -> str:
            return s.lower().replace(" ", "-")
    """)
    violations = check_gp001_duplicates(tmp_path)
    assert violations == []
