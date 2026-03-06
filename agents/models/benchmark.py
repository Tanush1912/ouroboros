"""Performance benchmark models — samples, results, and regression comparison."""

from typing import Literal

from pydantic import BaseModel, Field


class BenchmarkSampleResult(BaseModel):
    name: str = Field(description="Benchmark test name")
    mean_ms: float = Field(description="Mean execution time in milliseconds")
    stddev_ms: float = Field(default=0.0, description="Standard deviation in milliseconds")
    rounds: int = Field(default=1, description="Number of benchmark rounds")
    min_ms: float = Field(default=0.0, description="Minimum execution time in milliseconds")
    max_ms: float = Field(default=0.0, description="Maximum execution time in milliseconds")


class BenchmarkResult(BaseModel):
    samples: list[BenchmarkSampleResult] = Field(
        default_factory=list, description="Individual benchmark samples"
    )
    total_duration_seconds: float = Field(default=0.0, description="Total benchmark suite duration")
    timestamp: str = Field(default="", description="ISO 8601 timestamp of benchmark run")
    suite_name: str = Field(default="default", description="Benchmark suite identifier")
    baseline_commit_sha: str | None = Field(
        default=None, description="Git commit SHA this baseline was captured at"
    )


class PerfComparisonResult(BaseModel):
    baseline: BenchmarkResult | None = Field(default=None, description="Baseline benchmark result")
    current: BenchmarkResult = Field(description="Current benchmark result")
    regressions: list[str] = Field(
        default_factory=list, description="Benchmark names that regressed"
    )
    improvements: list[str] = Field(
        default_factory=list, description="Benchmark names that improved"
    )
    verdict: Literal["pass", "regressed", "no_baseline"] = Field(
        description="Overall verdict: pass if no regressions, regressed if threshold exceeded, no_baseline if first run"
    )
