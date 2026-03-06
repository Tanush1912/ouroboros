"""Benchmark tools — run pytest-benchmark suites and compare results."""

import json
import time
from datetime import UTC, datetime

from pydantic_ai import tool

from agents.core.paths import repo_root as _repo_root
from agents.models.benchmark import BenchmarkResult, BenchmarkSampleResult, PerfComparisonResult
from agents.tools.shell import _run


@tool
def run_benchmark(
    suite_path: str = "benchmarks/",
    marker: str = "benchmark",
) -> BenchmarkResult:
    """Run benchmark suite. Uses pytest-benchmark JSON output if available, else simple timing."""
    root = _repo_root()
    bench_output = "/tmp/bench.json"

    start = time.monotonic()
    returncode, _stdout, _stderr = _run(
        [
            "python",
            "-m",
            "pytest",
            suite_path,
            "-m",
            marker,
            f"--benchmark-json={bench_output}",
            "--benchmark-disable-gc",
            "-q",
        ],
        cwd=root,
    )
    duration = time.monotonic() - start

    samples: list[BenchmarkSampleResult] = []

    if returncode == 0:
        try:
            with open(bench_output) as f:
                data = json.load(f)
            for bench in data.get("benchmarks", []):
                stats = bench.get("stats", {})
                samples.append(
                    BenchmarkSampleResult(
                        name=bench.get("name", "unknown"),
                        mean_ms=stats.get("mean", 0) * 1000,
                        stddev_ms=stats.get("stddev", 0) * 1000,
                        rounds=stats.get("rounds", 1),
                        min_ms=stats.get("min", 0) * 1000,
                        max_ms=stats.get("max", 0) * 1000,
                    )
                )
        except (FileNotFoundError, json.JSONDecodeError, KeyError):
            samples.append(
                BenchmarkSampleResult(
                    name=f"suite:{suite_path}",
                    mean_ms=duration * 1000,
                    rounds=1,
                    min_ms=duration * 1000,
                    max_ms=duration * 1000,
                )
            )
    else:
        samples.append(
            BenchmarkSampleResult(
                name=f"suite:{suite_path}",
                mean_ms=duration * 1000,
                rounds=1,
                min_ms=duration * 1000,
                max_ms=duration * 1000,
            )
        )

    return BenchmarkResult(
        samples=samples,
        total_duration_seconds=duration,
        timestamp=datetime.now(UTC).isoformat(),
        suite_name=marker,
    )


@tool
def compare_benchmarks(
    baseline: BenchmarkResult,
    current: BenchmarkResult,
    threshold_pct: float = 10.0,
) -> PerfComparisonResult:
    """Compare two benchmark results. Pure function — no I/O."""
    if not baseline.samples:
        return PerfComparisonResult(
            baseline=baseline,
            current=current,
            verdict="no_baseline",
        )

    baseline_map = {s.name: s for s in baseline.samples}
    regressions: list[str] = []
    improvements: list[str] = []

    for sample in current.samples:
        base = baseline_map.get(sample.name)
        if base is None or base.mean_ms == 0:
            continue
        pct_change = ((sample.mean_ms - base.mean_ms) / base.mean_ms) * 100
        if pct_change > threshold_pct:
            regressions.append(
                f"{sample.name}: {pct_change:+.1f}% ({base.mean_ms:.1f}ms -> {sample.mean_ms:.1f}ms)"
            )
        elif pct_change < -threshold_pct:
            improvements.append(
                f"{sample.name}: {pct_change:+.1f}% ({base.mean_ms:.1f}ms -> {sample.mean_ms:.1f}ms)"
            )

    verdict = "regressed" if regressions else "pass"

    return PerfComparisonResult(
        baseline=baseline,
        current=current,
        regressions=regressions,
        improvements=improvements,
        verdict=verdict,
    )
