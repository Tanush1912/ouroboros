"""Reviewer agent output models."""

from typing import Literal

from pydantic import BaseModel, Field


class ReviewComment(BaseModel):
    file: str = Field(description="File path the comment applies to")
    line: int | None = Field(default=None, description="Line number, if specific")
    severity: Literal["nit", "minor", "major", "blocking"] = Field(
        description="How critical this comment is"
    )
    comment: str = Field(description="The review comment")
    suggested_fix: str | None = Field(
        default=None, description="Concrete suggested fix, if applicable"
    )


class ReviewOutput(BaseModel):
    approved: bool = Field(description="True if the PR is approved for merge")
    comments: list[ReviewComment] = Field(description="All review comments")
    blocking_issues: list[str] = Field(
        description="Issues that must be resolved before merge"
    )
    summary: str = Field(description="One-paragraph review summary")
    arch_violations: list[str] = Field(
        default_factory=list,
        description="Any architectural violations detected (ARCH-VIOLATION messages)",
    )
