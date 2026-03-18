"""Validator worker — runs tests, lint, and test quality gate, returns ValidationOutput.

The next_action field drives LangGraph conditional routing. No string parsing.
next_action is determined deterministically from test/lint/quality results — no LLM call needed.
"""

import logfire

from agents.models.implementer import FileChange
from agents.models.test_quality import TestQualityResult
from agents.models.validator import (
    LintResult,
    TestResult,
    ValidationOutput,
    determine_next_action,
)
from agents.tools.shell import run_lint, run_tests
from agents.tools.test_quality import analyze_test_quality


async def run_validator(
    iteration: int = 1,
    files_changed: list[FileChange] | None = None,
) -> ValidationOutput:
    """Run tests, lint, and test quality gate. Returns structured validation result."""
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

        # Run test quality gate if we have changed files to analyze
        quality: TestQualityResult | None = None
        if files_changed and test_result.passed:
            quality = analyze_test_quality(files_changed)
            logfire.info(
                "test_quality_analyzed",
                score=quality.score,
                passed=quality.passed,
                trivial_count=quality.trivial_test_count,
                assertion_density=quality.assertion_density,
            )

        overall_pass = test_result.passed and ruff_lint_result.passed and arch_lint_result.passed
        if quality is not None and not quality.passed:
            overall_pass = False

        next_action, failure_summary = determine_next_action(
            test_result, ruff_lint_result, arch_lint_result, iteration, quality
        )

        final = ValidationOutput(
            tests=test_result,
            lint=ruff_lint_result,
            arch_lint=arch_lint_result,
            overall_pass=overall_pass,
            next_action=next_action,
            failure_summary=failure_summary,
            test_quality=quality,
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
