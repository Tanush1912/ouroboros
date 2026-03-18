"""Validator worker — runs tests, lint, and test quality gate, returns ValidationOutput.

The next_action field drives LangGraph conditional routing. No string parsing.
next_action is determined deterministically from test/lint/quality results — no LLM call needed.

Tests and lint run in parallel via asyncio for faster validation cycles.
"""

import asyncio

import logfire

from agents.core.paths import repo_root as _repo_root
from agents.models.contracts import BehavioralSpec, ContractVerificationResult
from agents.models.implementer import FileChange
from agents.models.test_quality import TestQualityResult
from agents.models.validator import (
    LintResult,
    TestResult,
    ValidationOutput,
    determine_next_action,
)
from agents.tools.contract_verifier import verify_contracts
from agents.tools.shell import run_lint, run_tests
from agents.tools.test_quality import analyze_test_quality


async def run_validator(
    iteration: int = 1,
    files_changed: list[FileChange] | None = None,
    behavioral_specs: list[BehavioralSpec] | None = None,
    skip_quality_gate: bool = False,
) -> ValidationOutput:
    """Run tests, lint, and test quality gate. Returns structured validation result."""
    with logfire.span("validator", iteration=iteration):
        # Run tests and lint in parallel — they're independent
        loop = asyncio.get_event_loop()
        test_future = loop.run_in_executor(None, run_tests, ".")
        lint_future = loop.run_in_executor(None, run_lint, ".")
        test_result, lint_result = await asyncio.gather(test_future, lint_future)

        # Run anchor tests separately — failure always escalates
        anchors_dir = _repo_root() / "tests" / "anchors"
        if anchors_dir.exists() and any(anchors_dir.glob("test_*.py")):
            anchor_result: TestResult = run_tests("tests/anchors/")
            if not anchor_result.passed:
                logfire.warning("anchor_tests_failed", failures=anchor_result.failures[:5])
                return ValidationOutput(
                    tests=anchor_result,
                    lint=LintResult(passed=True, violations=[]),
                    arch_lint=LintResult(passed=True, violations=[]),
                    overall_pass=False,
                    next_action="escalate",
                    failure_summary="Anchor test failure (human-authored invariant):\n"
                    + "\n".join(anchor_result.failures[:5]),
                )

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

        # Run test quality gate — skip when planner says test_writer is skipped
        quality: TestQualityResult | None = None
        if files_changed and test_result.passed and not skip_quality_gate:
            quality = analyze_test_quality(files_changed)
            logfire.info(
                "test_quality_analyzed",
                score=quality.score,
                passed=quality.passed,
                trivial_count=quality.trivial_test_count,
                assertion_density=quality.assertion_density,
            )

        # Run behavioral contract verification if specs provided
        contract_result: ContractVerificationResult | None = None
        if behavioral_specs and test_result.passed:
            contract_result = verify_contracts(behavioral_specs)
            logfire.info(
                "contracts_verified",
                pass_rate=contract_result.pass_rate,
                passed=contract_result.passed,
                total=len(contract_result.checks),
            )

        overall_pass = test_result.passed and ruff_lint_result.passed and arch_lint_result.passed
        if quality is not None and not quality.passed:
            overall_pass = False
        if contract_result is not None and not contract_result.passed:
            overall_pass = False

        next_action, failure_summary = determine_next_action(
            test_result, ruff_lint_result, arch_lint_result, iteration, quality, contract_result
        )

        final = ValidationOutput(
            tests=test_result,
            lint=ruff_lint_result,
            arch_lint=arch_lint_result,
            overall_pass=overall_pass,
            next_action=next_action,
            failure_summary=failure_summary,
            test_quality=quality,
            contracts=contract_result,
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
