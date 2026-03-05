"""Observability query tools.

Agents can query their own observability stack. Requires the harness Docker stack running.
VictoriaLogs at :9428 (LogQL), VictoriaMetrics at :8428 (PromQL).
"""

import os

import httpx
from pydantic import BaseModel, Field
from pydantic_ai import tool

VICTORIA_LOGS_URL = os.environ.get("VICTORIA_LOGS_URL", "http://localhost:9428")
VICTORIA_METRICS_URL = os.environ.get("VICTORIA_METRICS_URL", "http://localhost:8428")


class LogLine(BaseModel):
    timestamp: str
    stream: dict[str, str] = Field(description="Log stream labels")
    message: str


class MetricSample(BaseModel):
    timestamp: float
    value: float


class MetricSeries(BaseModel):
    labels: dict[str, str]
    samples: list[MetricSample]


class MetricResult(BaseModel):
    query: str
    series: list[MetricSeries]


@tool
async def query_logs(logql: str, duration: str = "1h") -> list[LogLine]:
    """Query VictoriaLogs with LogQL. E.g. '{service="api"} |= "error"'"""
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{VICTORIA_LOGS_URL}/select/logsql/query",
            params={"query": logql, "duration": duration},
            timeout=30.0,
        )
        response.raise_for_status()
        data = response.json()

    lines = []
    for entry in data.get("streams", []):
        stream = entry.get("stream", {})
        for ts, msg in entry.get("values", []):
            lines.append(LogLine(timestamp=ts, stream=stream, message=msg))
    return lines


@tool
async def query_metrics(promql: str, duration: str = "1h") -> MetricResult:
    """Query VictoriaMetrics with PromQL. E.g. 'rate(http_requests_total[5m])'"""
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{VICTORIA_METRICS_URL}/api/v1/query_range",
            params={"query": promql, "duration": duration},
            timeout=30.0,
        )
        response.raise_for_status()
        data = response.json()

    series = []
    for result in data.get("data", {}).get("result", []):
        labels = result.get("metric", {})
        samples = [
            MetricSample(timestamp=ts, value=float(val)) for ts, val in result.get("values", [])
        ]
        series.append(MetricSeries(labels=labels, samples=samples))
    return MetricResult(query=promql, series=series)
