"""Tests for harness models — ProbeResult and AppStartupResult."""

from agents.models.harness import AppStartupResult, ProbeResult


def test_probe_result_healthy() -> None:
    probe = ProbeResult.model_validate(
        {
            "url": "http://localhost:8000/health",
            "status_code": 200,
            "healthy": True,
            "response_body": '{"status": "ok"}',
            "latency_ms": 12.5,
        }
    )
    assert probe.healthy is True
    assert probe.status_code == 200
    assert probe.error is None


def test_probe_result_unhealthy() -> None:
    probe = ProbeResult.model_validate(
        {
            "url": "http://localhost:8000/health",
            "healthy": False,
            "error": "Connection refused",
        }
    )
    assert probe.healthy is False
    assert probe.status_code is None


def test_probe_result_round_trip() -> None:
    probe = ProbeResult(
        url="http://localhost:8000/health",
        status_code=503,
        healthy=False,
        response_body="Service Unavailable",
        latency_ms=250.0,
        error="status 503",
    )
    data = probe.model_dump()
    restored = ProbeResult.model_validate(data)
    assert restored == probe


def test_app_startup_result_success() -> None:
    result = AppStartupResult.model_validate(
        {
            "container_name": "ouroboros-app-dev",
            "started": True,
            "health_url": "http://localhost:8000/health",
            "health_status": {
                "url": "http://localhost:8000/health",
                "status_code": 200,
                "healthy": True,
                "latency_ms": 5.0,
            },
            "startup_time_seconds": 3.2,
        }
    )
    assert result.started is True
    assert result.health_status is not None
    assert result.health_status.healthy is True


def test_app_startup_result_failure() -> None:
    result = AppStartupResult.model_validate(
        {
            "container_name": "ouroboros-app-dev",
            "started": False,
            "error": "Docker is not available on this system",
        }
    )
    assert result.started is False
    assert result.error is not None
    assert result.health_status is None
