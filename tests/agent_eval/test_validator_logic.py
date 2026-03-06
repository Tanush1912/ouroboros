"""Tests for the deterministic validator logic (_determine_next_action)."""

from agents.models.validator import LintResult, TestResult, determine_next_action


def test_all_pass_proceeds() -> None:
    action, summary = determine_next_action(
        TestResult(passed=True, failures=[]),
        LintResult(passed=True, violations=[]),
        LintResult(passed=True, violations=[]),
        iteration=1,
    )
    assert action == "proceed"
    assert summary == ""


def test_test_failure_retries() -> None:
    action, summary = determine_next_action(
        TestResult(passed=False, failures=["FAILED test_foo.py::test_bar - AssertionError"]),
        LintResult(passed=True, violations=[]),
        LintResult(passed=True, violations=[]),
        iteration=1,
    )
    assert action == "retry"
    assert "FAILED" in summary


def test_lint_failure_retries() -> None:
    action, summary = determine_next_action(
        TestResult(passed=True, failures=[]),
        LintResult(passed=False, violations=["E501 line too long"]),
        LintResult(passed=True, violations=[]),
        iteration=1,
    )
    assert action == "retry"
    assert "E501" in summary


def test_arch_lint_failure_retries() -> None:
    action, summary = determine_next_action(
        TestResult(passed=True, failures=[]),
        LintResult(passed=True, violations=[]),
        LintResult(passed=False, violations=["ARCH-001: workers cannot cross-import"]),
        iteration=1,
    )
    assert action == "retry"
    assert "ARCH-001" in summary


def test_import_error_escalates() -> None:
    action, summary = determine_next_action(
        TestResult(passed=False, failures=["ModuleNotFoundError: No module named 'foo'"]),
        LintResult(passed=True, violations=[]),
        LintResult(passed=True, violations=[]),
        iteration=1,
    )
    assert action == "escalate"
    assert "ModuleNotFoundError" in summary


def test_missing_module_escalates() -> None:
    action, _summary = determine_next_action(
        TestResult(passed=False, failures=["ImportError: cannot import name 'bar'"]),
        LintResult(passed=True, violations=[]),
        LintResult(passed=True, violations=[]),
        iteration=1,
    )
    assert action == "escalate"
