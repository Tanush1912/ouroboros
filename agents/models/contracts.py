"""Behavioral contract models — planner-emitted, deterministically verified.

BehavioralSpecs are emitted by the planner as part of the plan, then
verified by the contract verifier with zero LLM cost. They provide a
minimum behavioral coverage guarantee independent of AI-written test quality.
"""

from typing import Literal

from pydantic import BaseModel, Field


class BehavioralSpec(BaseModel):
    description: str = Field(description="What this contract verifies")
    kind: Literal[
        "import_check",
        "function_exists",
        "callable_returns",
        "endpoint_returns",
        "error_raises",
        "file_exists",
    ] = Field(description="Type of verification to perform")
    target: str = Field(description="Module path, function name, endpoint URL, or file path")
    args: list[str] = Field(default_factory=list, description="Arguments for callable checks")
    expected: str = Field(description="Expected value, type, status code, or exception class")


class ContractCheckResult(BaseModel):
    spec_description: str = Field(description="The contract description that was checked")
    passed: bool
    actual: str = Field(description="What was actually observed")
    error: str | None = Field(default=None, description="Error message if check failed")


class ContractVerificationResult(BaseModel):
    passed: bool = Field(description="True if all contracts pass")
    checks: list[ContractCheckResult] = Field(default_factory=list)
    pass_rate: float = Field(description="Fraction of contracts that passed (0.0-1.0)")
