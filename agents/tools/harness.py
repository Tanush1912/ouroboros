"""Runtime harness tools — app startup verification and HTTP endpoint probing.

Requires Docker and httpx. Gracefully returns failure results if unavailable.
"""

import shutil
import subprocess
import time

from agents.core.paths import repo_root as _repo_root
from agents.models.harness import AppStartupResult, ProbeResult


def run_app_and_probe(
    compose_file: str = "harness/sandbox/docker-compose.yml",
    health_path: str = "/health",
    timeout_seconds: int = 30,
) -> AppStartupResult:
    """Start app via docker compose and probe the health endpoint."""
    if not shutil.which("docker"):
        return AppStartupResult(
            container_name="unknown",
            started=False,
            error="Docker is not available on this system",
        )

    root = _repo_root()
    compose_path = root / compose_file
    if not compose_path.exists():
        return AppStartupResult(
            container_name="unknown",
            started=False,
            error=f"Compose file not found: {compose_file}",
        )

    import os

    container_name = f"ouroboros-app-{os.environ.get('WORKTREE_NAME', 'dev')}"
    app_port = os.environ.get("APP_PORT", "8000")
    health_url = f"http://localhost:{app_port}{health_path}"

    start = time.monotonic()
    result = subprocess.run(
        ["docker", "compose", "-f", str(compose_path), "up", "-d"],
        capture_output=True,
        text=True,
        cwd=root,
    )
    if result.returncode != 0:
        return AppStartupResult(
            container_name=container_name,
            started=False,
            health_url=health_url,
            error=f"docker compose up failed: {result.stderr[:500]}",
        )

    probe = _poll_health(health_url, timeout_seconds)
    startup_time = time.monotonic() - start

    return AppStartupResult(
        container_name=container_name,
        started=probe.healthy,
        health_url=health_url,
        health_status=probe,
        startup_time_seconds=startup_time,
        error=None if probe.healthy else probe.error,
    )


def _poll_health(url: str, timeout_seconds: int) -> ProbeResult:
    """Poll health endpoint with retries until healthy or timeout."""
    import httpx
    from tenacity import retry, stop_after_delay, wait_fixed

    last_error = ""

    @retry(stop=stop_after_delay(timeout_seconds), wait=wait_fixed(2), reraise=True)
    def _attempt() -> ProbeResult:
        nonlocal last_error
        start = time.monotonic()
        resp = httpx.get(url, timeout=5.0)
        latency = (time.monotonic() - start) * 1000
        if resp.status_code == 200:
            return ProbeResult(
                url=url,
                status_code=resp.status_code,
                healthy=True,
                response_body=resp.text[:500],
                latency_ms=latency,
            )
        last_error = f"status {resp.status_code}"
        raise RuntimeError(last_error)

    try:
        return _attempt()
    except Exception as e:
        last_error = last_error or str(e)
        return ProbeResult(url=url, healthy=False, error=f"Health check timed out: {last_error}")


def probe_endpoint(
    url: str,
    method: str = "GET",
    expected_status: int = 200,
    body: str | None = None,
) -> ProbeResult:
    """Send a single HTTP request and return structured result with latency."""
    import httpx

    try:
        start = time.monotonic()
        resp = httpx.request(method, url, content=body, timeout=10.0)
        latency = (time.monotonic() - start) * 1000
        return ProbeResult(
            url=url,
            status_code=resp.status_code,
            healthy=resp.status_code == expected_status,
            response_body=resp.text[:500],
            latency_ms=latency,
        )
    except Exception as e:
        return ProbeResult(url=url, healthy=False, error=str(e))
