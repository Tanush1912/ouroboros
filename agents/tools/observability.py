"""Observability query tools.

Agents can query their own observability stack. Requires the harness Docker stack running.
VictoriaLogs at :9428 (LogQL), VictoriaMetrics at :8428 (PromQL).

URLs are read at call time (not import time) so per-worktree env vars work
when set after module import.
"""

import os
from typing import Any

import httpx
from pydantic import BaseModel, Field


def _victoria_logs_url() -> str:
    return os.environ.get("VICTORIA_LOGS_URL", "http://localhost:9428")


def _victoria_metrics_url() -> str:
    return os.environ.get("VICTORIA_METRICS_URL", "http://localhost:8428")


class LogLineSchema(BaseModel):
    timestamp: str
    stream: dict[str, str] = Field(description="Log stream labels")
    message: str


class MetricSampleSchema(BaseModel):
    timestamp: float
    value: float


class MetricSeriesSchema(BaseModel):
    labels: dict[str, str]
    samples: list[MetricSampleSchema]


class MetricResult(BaseModel):
    query: str
    series: list[MetricSeriesSchema]


class _LogStreamSchema(BaseModel):
    stream: dict[str, str] = Field(default_factory=dict)
    values: list[list[str]] = Field(default_factory=list)


class _VictoriaLogsSchema(BaseModel):
    streams: list[_LogStreamSchema] = Field(default_factory=list)


class _MetricSeriesRawSchema(BaseModel):
    metric: dict[str, str] = Field(default_factory=dict)
    values: list[list[Any]] = Field(default_factory=list)


class _MetricDataSchema(BaseModel):
    result: list[_MetricSeriesRawSchema] = Field(default_factory=list)


class _VictoriaMetricsSchema(BaseModel):
    data: _MetricDataSchema = Field(default_factory=_MetricDataSchema)


async def _check_health(url: str) -> bool:
    """Quick pre-flight check — returns False if stack is unreachable (2s timeout)."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{url}/health", timeout=2.0)
            return resp.status_code == 200
    except Exception:
        return False


async def query_logs(logql: str, duration: str = "1h") -> list[LogLineSchema]:
    """Query VictoriaLogs with LogQL. E.g. '{service="api"} |= "error"'"""
    logs_url = _victoria_logs_url()
    if not await _check_health(logs_url):
        return []

    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{logs_url}/select/logsql/query",
            params={"query": logql, "duration": duration},
            timeout=30.0,
        )
        response.raise_for_status()
        parsed = _VictoriaLogsSchema.model_validate(response.json())

    lines = []
    for entry in parsed.streams:
        for val in entry.values:
            if len(val) >= 2:
                lines.append(LogLineSchema(timestamp=val[0], stream=entry.stream, message=val[1]))
    return lines


async def query_metrics(promql: str, duration: str = "1h") -> MetricResult:
    """Query VictoriaMetrics with PromQL. E.g. 'rate(http_requests_total[5m])'"""
    metrics_url = _victoria_metrics_url()
    if not await _check_health(metrics_url):
        return MetricResult(query=promql, series=[])

    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{metrics_url}/api/v1/query_range",
            params={"query": promql, "duration": duration},
            timeout=30.0,
        )
        response.raise_for_status()
        parsed = _VictoriaMetricsSchema.model_validate(response.json())

    series = []
    for result in parsed.data.result:
        samples = [
            MetricSampleSchema(timestamp=v[0], value=float(v[1]))
            for v in result.values
            if len(v) >= 2
        ]
        series.append(MetricSeriesSchema(labels=result.metric, samples=samples))
    return MetricResult(query=promql, series=series)
