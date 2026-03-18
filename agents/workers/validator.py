"""Validator worker — runs tests and lint, returns ValidationOutput.

The next_action field drives LangGraph conditional routing. No string parsing.
next_action is determined deterministically from test/lint results — no LLM call needed.
"""

import logfire

from agents.models.validator import (
    LintResult,
    TestResult,
    ValidationOutput,
    determine_next_action,
)
from agents.tools.shell import run_lint, run_tests


async def run_validator(
    iteration: int = 1,
) -> ValidationOutput:
    """Run tests and lint on the implementation, return structured validation result."""
    with logfire.span("validator", iteration=iteration):
        test_result: TestResult = run_tests(".")
        lint_result: LintResult = run_lint(".")

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
        next_action, failure_summary = determine_next_action(
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
