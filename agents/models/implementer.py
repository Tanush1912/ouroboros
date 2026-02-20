"""Implementer agent output models."""

from typing import Literal

from pydantic import BaseModel, Field


class FileChange(BaseModel):
    path: str = Field(description="Relative path from repo root")
    operation: Literal["create", "modify", "delete"] = Field(
        description="What operation was performed"
    )
    content: str | None = Field(
        default=None,
        description="New file content. None for delete operations.",
    )
    diff_summary: str = Field(description="Human-readable summary of what changed")


class ImplementOutput(BaseModel):
    files_changed: list[FileChange] = Field(
        description="All files created, modified, or deleted"
    )
    commit_message: str = Field(description="Conventional commit message for these changes")
    implementation_notes: str = Field(
        description="Notes on implementation decisions, trade-offs, or limitations"
    )
    test_commands: list[str] = Field(
        description="Shell commands to verify the implementation"
    )
