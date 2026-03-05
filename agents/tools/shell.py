"""Shell tools — test/lint/build runners.

All tools return structured Pydantic models. No raw stdout parsing.
"""

import shlex
import subprocess
from pathlib import Path

from pydantic import BaseModel, Field
from pydantic_ai import tool

from agents.core.paths import repo_root as _repo_root
from agents.models.validator import LintResult, TestResult


class BuildResult(BaseModel):
    success: bool
    log: str = Field(description="Build output (stdout + stderr)")
    duration_seconds: float


class CommandResult(BaseModel):
    returncode: int
    stdout: str
    stderr: str
    success: bool


def _run(cmd: list[str], cwd: Path | None = None) -> tuple[int, str, str]:
    result = subprocess.run(
        cmd, capture_output=True, text=True, cwd=cwd or _repo_root()
    )
    return result.returncode, result.stdout, result.stderr


@tool
def run_tests(path: str = ".") -> TestResult:
    """Run pytest. Returns structured pass/fail with failure details."""
    import time
    start = time.monotonic()
    returncode, stdout, stderr = _run(
        ["python", "-m", "pytest", path, "--tb=short", "-q"],
        cwd=_repo_root(),
    )
    duration = time.monotonic() - start
    passed = returncode == 0
    failures = []
    if not passed:
        for line in (stdout + stderr).splitlines():
            if line.startswith("FAILED") or "AssertionError" in line or "Error" in line:
                failures.append(line.strip())
    return TestResult(passed=passed, failures=failures, duration_seconds=duration)


@tool
def run_lint(path: str = ".") -> LintResult:
    """Run ruff + arch_lint + golden_lint. Returns violations with AGENT_REMEDIATION instructions."""
    root = _repo_root()
    violations = []
    auto_fixed = 0

    returncode, stdout, _stderr = _run(["python", "-m", "ruff", "check", path], cwd=root)
    if returncode != 0:
        for line in stdout.splitlines():
            if line.strip():
                violations.append(f"RUFF: {line.strip()}")

    returncode, stdout, _stderr = _run(
        ["python", "lint/run_lint.py", "--arch-only", path], cwd=root
    )
    if returncode != 0:
        violations.extend(stdout.splitlines())

    returncode, stdout, _stderr = _run(
        ["python", "lint/run_lint.py", "--golden-only", path], cwd=root
    )
    if returncode != 0:
        violations.extend(stdout.splitlines())

    return LintResult(passed=len(violations) == 0, violations=violations, auto_fixed=auto_fixed)


@tool
def run_build() -> BuildResult:
    """Build the application. Returns success/failure + build log."""
    import time
    start = time.monotonic()
    returncode, stdout, stderr = _run(["python", "-m", "build"])
    duration = time.monotonic() - start
    return BuildResult(
        success=returncode == 0,
        log=(stdout + stderr)[:4000],
        duration_seconds=duration,
    )


@tool
def run_command(command: str, cwd: str = ".") -> CommandResult:
    """Run an arbitrary shell command. Use sparingly — prefer specific tools."""
    root = _repo_root()
    work_dir = (root / cwd).resolve()
    result = subprocess.run(
        shlex.split(command), capture_output=True, text=True, cwd=work_dir
    )
    return CommandResult(
        returncode=result.returncode,
        stdout=result.stdout[:4000],
        stderr=result.stderr[:4000],
        success=result.returncode == 0,
    )
