"""Validator agent output models.

The next_action field on ValidationOutput drives LangGraph conditional edges.
No string parsing — pure type routing.
"""

from typing import Literal

from pydantic import BaseModel, Field

from agents.models.contracts import ContractVerificationResult
from agents.models.test_quality import TestQualityResult


class TestResult(BaseModel):
    passed: bool = Field(description="True if all tests passed")
    failures: list[str] = Field(description="Test failure messages")
    coverage: float | None = Field(default=None, description="Code coverage percentage (0-100)")
    duration_seconds: float = Field(default=0.0, description="Test run duration")


class LintResult(BaseModel):
    passed: bool = Field(description="True if lint found no violations")
    violations: list[str] = Field(
        description="Violation messages. Arch violations include AGENT_REMEDIATION instructions."
    )
    auto_fixed: int = Field(default=0, description="Number of violations auto-fixed by ruff")


class ValidationOutput(BaseModel):
    tests: TestResult
    lint: LintResult
    arch_lint: LintResult
    overall_pass: bool = Field(description="True only if tests, lint, and arch_lint all passed")
    next_action: Literal["proceed", "retry", "escalate"] = Field(
        description=(
            "proceed: all checks pass, ready for PR. "
            "retry: fixable failures, agent should try again. "
            "escalate: unrecoverable or max iterations hit."
        )
    )
    test_quality: TestQualityResult | None = Field(
        default=None,
        description="AST-based test quality assessment (None if not yet analyzed)",
    )
    contracts: ContractVerificationResult | None = Field(
        default=None,
        description="Behavioral contract verification results (None if no specs)",
    )
    failure_summary: str = Field(
        default="",
        description="Human-readable summary of what failed and why",
    )


def determine_next_action(
    test_result: TestResult,
    lint_result: LintResult,
    arch_lint_result: LintResult,
    iteration: int,
    test_quality: TestQualityResult | None = None,
    contracts: ContractVerificationResult | None = None,
) -> tuple[str, str]:
    """Deterministically compute next_action and failure_summary from results.

    Pure function — no LLM call, no I/O.
    """
    # Hard failures first
    failures = []
    if not test_result.passed:
        failures.extend(test_result.failures[:5])
    if not lint_result.passed:
        failures.extend(lint_result.violations[:3])
    if not arch_lint_result.passed:
        failures.extend(arch_lint_result.violations[:3])

    if failures:
        unrecoverable = (
            "ModuleNotFoundError",
            "ImportError",
            "missing external",
            "No module named",
        )
        for f in failures:
            for signal in unrecoverable:
                if signal in f:
                    return "escalate", "\n".join(failures)
        return "retry", "\n".join(failures)

    # Tests + lint pass — check contracts if available
    if contracts is not None and not contracts.passed:
        failed = [c for c in contracts.checks if not c.passed]
        contract_issues = [f"{c.spec_description}: {c.actual}" for c in failed[:5]]
        return "retry", "Behavioral contract failures:\n" + "\n".join(contract_issues)

    # Check test quality if available
    if test_quality is not None and not test_quality.passed:
        quality_issues = test_quality.details or [
            f"Test quality score: {test_quality.score:.0f}/100"
        ]
        return "retry", "Test quality gate failed:\n" + "\n".join(quality_issues)

    return "proceed", ""
