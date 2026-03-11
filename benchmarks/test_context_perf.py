"""Benchmark: context builder performance."""

import pytest


@pytest.mark.benchmark
def test_build_context_performance(benchmark):
    from agents.core.context_builder import build_context

    benchmark(build_context, "sample task for benchmarking")
