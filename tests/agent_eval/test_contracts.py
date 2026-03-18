"""Tests for the behavioral contract verifier."""

from agents.models.contracts import BehavioralSpec, ContractVerificationResult
from agents.tools.contract_verifier import verify_contracts


def test_import_check_passes_for_existing_module() -> None:
    spec = BehavioralSpec(
        description="os module loads",
        kind="import_check",
        target="os",
        expected="module",
    )
    result = verify_contracts([spec])
    assert result.passed
    assert result.checks[0].passed


def test_import_check_fails_for_missing_module() -> None:
    spec = BehavioralSpec(
        description="nonexistent module loads",
        kind="import_check",
        target="nonexistent_module_xyz",
        expected="module",
    )
    result = verify_contracts([spec])
    assert not result.passed
    assert not result.checks[0].passed
    assert "import failed" in result.checks[0].actual


def test_function_exists_passes() -> None:
    spec = BehavioralSpec(
        description="os.path.join exists",
        kind="function_exists",
        target="os.path.join",
        expected="function",
    )
    result = verify_contracts([spec])
    assert result.passed
    assert "exists" in result.checks[0].actual


def test_function_exists_fails_for_missing() -> None:
    spec = BehavioralSpec(
        description="os.nonexistent_func exists",
        kind="function_exists",
        target="os.nonexistent_func",
        expected="function",
    )
    result = verify_contracts([spec])
    assert not result.passed


def test_file_exists_passes(tmp_path) -> None:
    (tmp_path / "test_file.txt").write_text("hello", encoding="utf-8")
    spec = BehavioralSpec(
        description="test file exists",
        kind="file_exists",
        target="agents/core/guards.py",
        expected="exists",
    )
    result = verify_contracts([spec])
    assert result.passed


def test_file_exists_fails_for_missing() -> None:
    spec = BehavioralSpec(
        description="missing file",
        kind="file_exists",
        target="nonexistent/path/file.py",
        expected="exists",
    )
    result = verify_contracts([spec])
    assert not result.passed
    assert "not found" in result.checks[0].actual


def test_error_raises_passes() -> None:
    spec = BehavioralSpec(
        description="int() raises ValueError on bad input",
        kind="error_raises",
        target="builtins.int",
        args=["'not_a_number'"],
        expected="ValueError",
    )
    result = verify_contracts([spec])
    assert result.passed
    assert "ValueError" in result.checks[0].actual


def test_error_raises_fails_wrong_exception() -> None:
    spec = BehavioralSpec(
        description="int() raises TypeError on bad input",
        kind="error_raises",
        target="builtins.int",
        args=["'not_a_number'"],
        expected="TypeError",
    )
    result = verify_contracts([spec])
    assert not result.passed
    assert "ValueError" in result.checks[0].actual


def test_callable_returns_passes() -> None:
    spec = BehavioralSpec(
        description="len of empty list is 0",
        kind="callable_returns",
        target="builtins.len",
        args=["[]"],
        expected="0",
    )
    result = verify_contracts([spec])
    assert result.passed


def test_empty_specs_passes() -> None:
    result = verify_contracts([])
    assert result.passed
    assert result.pass_rate == 1.0


def test_pass_rate_calculated() -> None:
    specs = [
        BehavioralSpec(description="pass", kind="import_check", target="os", expected="module"),
        BehavioralSpec(
            description="fail", kind="import_check", target="nonexistent_xyz", expected="module"
        ),
    ]
    result = verify_contracts(specs)
    assert not result.passed
    assert result.pass_rate == 0.5


def test_determine_next_action_retries_on_contract_failure() -> None:
    from agents.models.contracts import ContractCheckResult
    from agents.models.validator import LintResult, TestResult, determine_next_action

    passing = TestResult(passed=True, failures=[])
    lint_ok = LintResult(passed=True, violations=[])
    failed_contracts = ContractVerificationResult(
        passed=False,
        checks=[
            ContractCheckResult(
                spec_description="module loads", passed=False, actual="import failed"
            )
        ],
        pass_rate=0.0,
    )
    action, summary = determine_next_action(
        passing, lint_ok, lint_ok, 1, contracts=failed_contracts
    )
    assert action == "retry"
    assert "contract" in summary.lower()
