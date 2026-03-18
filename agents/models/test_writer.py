"""Test writer agent output models.

The test writer is a dedicated agent that writes tests for code the
implementer produced. Separated from the implementer to create an
adversarial dynamic — the test writer tries to break the implementation.
"""

from pydantic import BaseModel, Field

from agents.models.implementer import FileChange


class TestStrategy(BaseModel):
    happy_paths: list[str] = Field(description="Happy path scenarios to test")
    error_paths: list[str] = Field(description="Error/exception scenarios to test")
    edge_cases: list[str] = Field(description="Edge case scenarios to test")


class TestWriterOutput(BaseModel):
    test_files: list[FileChange] = Field(description="Test files to create/modify (test_*.py only)")
    test_strategy: TestStrategy = Field(description="What the test writer plans to test")
    confidence: float = Field(description="Confidence that tests are comprehensive (0.0-1.0)")
