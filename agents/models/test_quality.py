"""Test quality assessment models.

Used by the AST-based test quality gate to evaluate AI-generated tests
before they can greenlight code. Catches degenerate tests with zero LLM cost.
"""

from pydantic import BaseModel, Field


class TestQualityResult(BaseModel):
    score: float = Field(description="Quality score 0-100")
    passed: bool = Field(description="True if score >= threshold (60)")
    assertion_density: float = Field(description="Average assert statements per test function")
    trivial_test_count: int = Field(description="Number of tests with banned patterns")
    untested_files: list[str] = Field(
        default_factory=list,
        description="Changed production files with no test importing them",
    )
    banned_patterns: list[str] = Field(
        default_factory=list,
        description="Detected banned patterns (assert True, pass body, etc.)",
    )
    edge_case_coverage: float = Field(
        description="Fraction of tests that exercise error/edge paths (0.0-1.0)"
    )
    details: list[str] = Field(
        default_factory=list,
        description="Human-readable details of quality issues found",
    )
