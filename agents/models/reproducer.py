"""Bug reproduction models — structured error context and reproduction results."""

from pydantic import BaseModel, Field


class ErrorContext(BaseModel):
    command: str = Field(description="Command that was executed")
    returncode: int = Field(description="Process return code")
    stdout: str = Field(default="", description="Standard output (truncated)")
    stderr: str = Field(default="", description="Standard error (truncated)")
    traceback: str = Field(default="", description="Extracted Python traceback")
    relevant_logs: list[str] = Field(default_factory=list, description="Relevant log lines")


class ReproductionResult(BaseModel):
    reproduced: bool = Field(description="True if the bug was successfully reproduced")
    steps_attempted: list[str] = Field(default_factory=list, description="Commands/steps attempted")
    error_context: ErrorContext | None = Field(
        default=None, description="Captured error details if reproduced"
    )
    summary: str = Field(default="", description="Human-readable summary of reproduction attempt")
