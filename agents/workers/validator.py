"""Validator worker — runs tests and lint, returns ValidationOutput.

The next_action field drives LangGraph conditional routing. No string parsing.
next_action is determined deterministically from test/lint results — no LLM call needed.
"""

import logfire

from agents.models.implementer import ImplementOutput
from agents.models.validator import LintResult, TestResult, ValidationOutput
from agents.tools.shell import run_lint, run_tests


def _determine_next_action(
    test_result: TestResult,
    lint_result: LintResult,
    arch_lint_result: LintResult,
    iteration: int,
) -> tuple[str, str]:
    """Deterministically compute next_action and failure_summary from results."""
    if test_result.passed and lint_result.passed and arch_lint_result.passed:
        return "proceed", ""

    failures = []
    if not test_result.passed:
        failures.extend(test_result.failures[:5])
    if not lint_result.passed:
        failures.extend(lint_result.violations[:3])
    if not arch_lint_result.passed:
        failures.extend(arch_lint_result.violations[:3])

    unrecoverable = ("ModuleNotFoundError", "ImportError", "missing external", "No module named")
    for f in failures:
        for signal in unrecoverable:
            if signal in f:
                return "escalate", "\n".join(failures)

    return "retry", "\n".join(failures)


async def run_validator(
    implement_output: ImplementOutput,
    iteration: int = 1,
) -> ValidationOutput:
    """Run tests and lint on the implementation, return structured validation result."""
    with logfire.span("validator", iteration=iteration):
        test_result: TestResult = run_tests.fn(".")
        lint_result: LintResult = run_lint.fn(".")

        arch_violations = [v for v in lint_result.violations if v.startswith("ARCH-")]
        other_violations = [v for v in lint_result.violations if not v.startswith("ARCH-")]

        arch_lint_result = LintResult(
            passed=len(arch_violations) == 0,
            violations=arch_violations,
        )
        ruff_lint_result = LintResult(
            passed=len(other_violations) == 0,
            violations=other_violations,
            auto_fixed=lint_result.auto_fixed,
        )

        overall_pass = test_result.passed and ruff_lint_result.passed and arch_lint_result.passed
        next_action, failure_summary = _determine_next_action(
            test_result, ruff_lint_result, arch_lint_result, iteration
        )

        final = ValidationOutput(
            tests=test_result,
            lint=ruff_lint_result,
            arch_lint=arch_lint_result,
            overall_pass=overall_pass,
            next_action=next_action,
            failure_summary=failure_summary,
        )

        logfire.info(
            "validation_complete",
            overall_pass=overall_pass,
            next_action=final.next_action,
            iteration=iteration,
            test_failures=len(test_result.failures),
            lint_violations=len(ruff_lint_result.violations),
        )
        return final
