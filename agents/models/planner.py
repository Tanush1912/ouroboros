"""Planner agent output models."""

from typing import Literal

from pydantic import BaseModel, Field

from agents.models.contracts import BehavioralSpec


class ExecutionStep(BaseModel):
    description: str = Field(description="What this step does")
    files_affected: list[str] = Field(description="Files this step reads or modifies")
    tool: Literal[
        "fs", "shell", "git", "browser", "observability", "index", "harness", "benchmark"
    ] = Field(description="Tool category this step uses")
    expected_output: str = Field(description="What a successful execution of this step produces")


class PlanOutput(BaseModel):
    task_summary: str = Field(description="One-sentence summary of the task")
    steps: list[ExecutionStep] = Field(description="Ordered sequence of execution steps")
    test_strategy: str = Field(description="How to verify the implementation is correct")
    risk_level: Literal["low", "medium", "high"] = Field(
        description="Estimated risk of this change"
    )
    requires_human_review: bool = Field(
        description="True if this task requires human review before merge"
    )
    affected_domains: list[str] = Field(
        default_factory=list,
        description="Which architectural domains this task touches",
    )
    requires_browser_validation: bool = Field(
        default=False,
        description="True if this task involves UI changes that need browser validation",
    )
    behavioral_specs: list[BehavioralSpec] = Field(
        default_factory=list,
        description=(
            "Machine-verifiable behavioral contracts. Include import_check for "
            "new modules, function_exists for new public functions, and at least "
            "one error_raises or callable_returns for behavioral verification."
        ),
    )
