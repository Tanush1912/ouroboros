"""Mutation sampling models — verify test effectiveness empirically.

Surviving mutants prove tests don't catch specific code changes.
These results are fed back to the test writer agent for targeted fixes.
"""

from pydantic import BaseModel, Field


class MutantResult(BaseModel):
    file: str = Field(description="File that was mutated")
    line: int = Field(description="Line number of the mutation")
    mutation: str = Field(description="Description of what was changed")
    survived: bool = Field(description="True if tests still passed with this mutation")


class MutationSamplingResult(BaseModel):
    total_mutants: int = Field(description="Number of mutations applied")
    killed: int = Field(description="Mutants caught by tests")
    survived: int = Field(description="Mutants NOT caught by tests")
    kill_rate: float = Field(description="killed / total (0.0-1.0)")
    passed: bool = Field(description="True if kill_rate >= 0.6")
    survivors: list[MutantResult] = Field(
        default_factory=list,
        description="Details of surviving mutants for test writer feedback",
    )
