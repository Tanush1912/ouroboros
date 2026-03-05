"""Validator agent output models.

The next_action field on ValidationOutput drives LangGraph conditional edges.
No string parsing — pure type routing.
"""

from typing import Literal

from pydantic import BaseModel, Field


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
    failure_summary: str = Field(
        default="",
        description="Human-readable summary of what failed and why",
    )
