"""Shell tools — test/lint/build runners.

All tools return structured Pydantic models. No raw stdout parsing.
"""

import shlex
import subprocess
from pathlib import Path

from pydantic import BaseModel, Field

from agents.core.paths import repo_root as _repo_root
from agents.models.reproducer import ErrorContext
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


def run_subprocess(
    cmd: list[str], cwd: Path | None = None, timeout: int = 300
) -> tuple[int, str, str]:
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, cwd=cwd or _repo_root(), timeout=timeout
        )
    except subprocess.TimeoutExpired:
        return 1, "", f"Command timed out after {timeout}s: {' '.join(cmd)}"
    return result.returncode, result.stdout, result.stderr


def run_tests(path: str = ".") -> TestResult:
    """Run pytest. Returns structured pass/fail with failure details."""
    import time

    start = time.monotonic()
    returncode, stdout, stderr = run_subprocess(
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


def run_lint(path: str = ".") -> LintResult:
    """Run ruff + arch_lint + golden_lint. Returns violations with AGENT_REMEDIATION instructions."""
    root = _repo_root()
    violations = []
    auto_fixed = 0

    returncode, stdout, _stderr = run_subprocess(["python", "-m", "ruff", "check", path], cwd=root)
    if returncode != 0:
        for line in stdout.splitlines():
            if line.strip():
                violations.append(f"RUFF: {line.strip()}")

    returncode, stdout, _stderr = run_subprocess(
        ["python", "lint/run_lint.py", "--arch-only", path], cwd=root
    )
    if returncode != 0:
        violations.extend(stdout.splitlines())

    returncode, stdout, _stderr = run_subprocess(
        ["python", "lint/run_lint.py", "--golden-only", path], cwd=root
    )
    if returncode != 0:
        violations.extend(stdout.splitlines())

    return LintResult(passed=len(violations) == 0, violations=violations, auto_fixed=auto_fixed)


def run_build() -> BuildResult:
    """Build the application. Returns success/failure + build log."""
    import time

    start = time.monotonic()
    returncode, stdout, stderr = run_subprocess(["python", "-m", "build"])
    duration = time.monotonic() - start
    return BuildResult(
        success=returncode == 0,
        log=(stdout + stderr)[:4000],
        duration_seconds=duration,
    )


def run_single_test(test_path: str) -> TestResult:
    """Run a single test file/function with full traceback for debugging."""
    import time

    start = time.monotonic()
    returncode, stdout, stderr = run_subprocess(
        ["python", "-m", "pytest", test_path, "--tb=long", "-v"],
        cwd=_repo_root(),
    )
    duration = time.monotonic() - start
    passed = returncode == 0
    failures = []
    if not passed:
        for line in (stdout + stderr).splitlines():
            if line.startswith("FAILED") or "Error" in line or "assert" in line.lower():
                failures.append(line.strip())
    return TestResult(passed=passed, failures=failures, duration_seconds=duration)


def extract_traceback(text: str) -> str:
    """Extract Python traceback from command output."""
    lines = text.splitlines()
    tb_start = None
    tb_end = None
    for i, line in enumerate(lines):
        if "Traceback (most recent call last):" in line:
            tb_start = i
        if tb_start is not None and i > tb_start and line and not line.startswith(" "):
            tb_end = i + 1
            break
    if tb_start is not None:
        end = tb_end if tb_end else len(lines)
        return "\n".join(lines[tb_start:end])
    return ""


def capture_error_context(command: str, cwd: str = ".") -> ErrorContext:
    """Run a command and capture structured error context including traceback."""
    root = _repo_root()
    work_dir = (root / cwd).resolve()
    try:
        work_dir.relative_to(root.resolve())
    except ValueError as err:
        raise ValueError(f"cwd '{cwd}' is outside the repository root") from err

    result = subprocess.run(shlex.split(command), capture_output=True, text=True, cwd=work_dir)
    combined = result.stdout + result.stderr
    traceback_text = extract_traceback(combined)

    relevant_logs = [
        line.strip()
        for line in combined.splitlines()
        if any(kw in line.lower() for kw in ("error", "failed", "exception", "assert"))
    ][:20]

    return ErrorContext(
        command=command,
        returncode=result.returncode,
        stdout=result.stdout[:4000],
        stderr=result.stderr[:4000],
        traceback=traceback_text,
        relevant_logs=relevant_logs,
    )


def run_command(command: str, cwd: str = ".") -> CommandResult:
    """Run an arbitrary shell command. Use sparingly — prefer specific tools."""
    root = _repo_root()
    work_dir = (root / cwd).resolve()
    try:
        work_dir.relative_to(root.resolve())
    except ValueError as err:
        raise ValueError(f"cwd '{cwd}' is outside the repository root") from err
    result = subprocess.run(shlex.split(command), capture_output=True, text=True, cwd=work_dir)
    return CommandResult(
        returncode=result.returncode,
        stdout=result.stdout[:4000],
        stderr=result.stderr[:4000],
        success=result.returncode == 0,
    )
