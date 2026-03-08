"""Post-mortem analysis output models.

Produced by the post-mortem worker after escalation/failure. Drives
automatic creation of harness-improvement GitHub issues.
"""

from typing import Literal

from pydantic import BaseModel, Field

FailureCategory = Literal[
    "missing_tool",
    "bad_prompt",
    "insufficient_context",
    "guard_limit",
    "validation_loop",
    "external_dependency",
    "unknown",
]


class HarnessImprovementOutput(BaseModel):
    category: FailureCategory = Field(description="Root cause category of the failure")
    failure_summary: str = Field(description="One-paragraph summary of what went wrong")
    root_cause: str = Field(
        description="Why the agent got stuck — the underlying gap in the harness"
    )
    affected_files: list[str] = Field(
        description="Harness files that need improvement (e.g. prompts, tools, guards)"
    )
    improvement: str = Field(description="Specific improvement recommendation")
    suggested_fix: str = Field(
        description="Concrete code/prompt change to implement the improvement"
    )
    priority: Literal["low", "medium", "high"] = Field(
        description="How urgently this improvement should be addressed"
    )
