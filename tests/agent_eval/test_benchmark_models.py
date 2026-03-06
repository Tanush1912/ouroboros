"""Tests for benchmark models — BenchmarkSampleResult, BenchmarkResult, PerfComparisonResult."""

from agents.models.benchmark import BenchmarkResult, BenchmarkSampleResult, PerfComparisonResult


def test_benchmark_sample_construction() -> None:
    sample = BenchmarkSampleResult.model_validate(
        {
            "name": "test_sort",
            "mean_ms": 12.5,
            "stddev_ms": 1.2,
            "rounds": 100,
            "min_ms": 10.0,
            "max_ms": 18.0,
        }
    )
    assert sample.name == "test_sort"
    assert sample.mean_ms == 12.5
    assert sample.rounds == 100


def test_benchmark_sample_defaults() -> None:
    sample = BenchmarkSampleResult(name="test_basic", mean_ms=5.0)
    assert sample.stddev_ms == 0.0
    assert sample.rounds == 1
    assert sample.min_ms == 0.0
    assert sample.max_ms == 0.0


def test_benchmark_result_construction() -> None:
    result = BenchmarkResult.model_validate(
        {
            "samples": [
                {"name": "test_a", "mean_ms": 10.0},
                {"name": "test_b", "mean_ms": 20.0},
            ],
            "total_duration_seconds": 1.5,
            "timestamp": "2026-03-06T00:00:00Z",
            "suite_name": "unit",
            "baseline_commit_sha": "abc123",
        }
    )
    assert len(result.samples) == 2
    assert result.baseline_commit_sha == "abc123"


def test_benchmark_result_defaults() -> None:
    result = BenchmarkResult()
    assert result.samples == []
    assert result.total_duration_seconds == 0.0
    assert result.baseline_commit_sha is None


def test_perf_comparison_pass() -> None:
    baseline = BenchmarkResult(
        samples=[
            BenchmarkSampleResult(name="test_a", mean_ms=10.0),
        ]
    )
    current = BenchmarkResult(
        samples=[
            BenchmarkSampleResult(name="test_a", mean_ms=10.5),
        ]
    )
    comparison = PerfComparisonResult.model_validate(
        {
            "baseline": baseline.model_dump(),
            "current": current.model_dump(),
            "regressions": [],
            "improvements": [],
            "verdict": "pass",
        }
    )
    assert comparison.verdict == "pass"
    assert len(comparison.regressions) == 0


def test_perf_comparison_regressed() -> None:
    comparison = PerfComparisonResult.model_validate(
        {
            "current": {"samples": [{"name": "test_a", "mean_ms": 25.0}]},
            "regressions": ["test_a: +150.0% (10.0ms -> 25.0ms)"],
            "verdict": "regressed",
        }
    )
    assert comparison.verdict == "regressed"
    assert len(comparison.regressions) == 1


def test_perf_comparison_no_baseline() -> None:
    comparison = PerfComparisonResult.model_validate(
        {
            "current": {"samples": []},
            "verdict": "no_baseline",
        }
    )
    assert comparison.verdict == "no_baseline"
    assert comparison.baseline is None


def test_perf_comparison_round_trip() -> None:
    comparison = PerfComparisonResult(
        baseline=BenchmarkResult(samples=[BenchmarkSampleResult(name="x", mean_ms=10.0)]),
        current=BenchmarkResult(samples=[BenchmarkSampleResult(name="x", mean_ms=9.0)]),
        regressions=[],
        improvements=["x: -10.0% (10.0ms -> 9.0ms)"],
        verdict="pass",
    )
    data = comparison.model_dump()
    restored = PerfComparisonResult.model_validate(data)
    assert restored == comparison
    assert len(restored.improvements) == 1
