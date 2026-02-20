"""Cleaner (entropy GC) agent output models."""

from typing import Literal

from pydantic import BaseModel, Field


class EntropyViolation(BaseModel):
    principle: str = Field(description="Golden Principle ID, e.g. 'GP-001'")
    file: str = Field(description="File where violation was detected")
    description: str = Field(description="Human-readable description of the violation")
    suggested_fix: str = Field(description="Concrete remediation steps")
    auto_fixable: bool = Field(
        description="True if the agent can fix this without human input"
    )
    severity: Literal["low", "medium", "high"] = Field(
        description="Violation severity"
    )


class CleanupOutput(BaseModel):
    violations: list[EntropyViolation] = Field(
        description="All detected Golden Principle violations"
    )
    quality_scores: dict[str, float] = Field(
        description="Per-domain quality scores from 0.0 to 10.0"
    )
    recommended_prs: list[str] = Field(
        description="One PR title/description per auto-fixable violation cluster"
    )
    human_review_needed: list[str] = Field(
        description="Non-auto-fixable issues requiring human attention"
    )

    def overall_score(self) -> float:
        if not self.quality_scores:
            return 10.0
        return sum(self.quality_scores.values()) / len(self.quality_scores)

    def has_blocking_violations(self) -> bool:
        return any(v.severity == "high" for v in self.violations)
