"""Tests for agents.server /health and /status endpoints."""

import json
import threading
from http.server import HTTPServer
from urllib.request import urlopen

from agents.server import _Handler


def _run_server():
    """Start server on a random port, return (server, base_url)."""
    server = HTTPServer(("127.0.0.1", 0), _Handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, f"http://127.0.0.1:{port}"


def test_health_endpoint():
    server, base = _run_server()
    try:
        resp = urlopen(f"{base}/health", timeout=5)
        data = json.loads(resp.read())
        assert resp.status == 200
        assert data == {"status": "ok"}
    finally:
        server.shutdown()


def test_status_endpoint():
    server, base = _run_server()
    try:
        resp = urlopen(f"{base}/status", timeout=5)
        data = json.loads(resp.read())
        assert resp.status == 200
        assert data["status"] == "ok"
        assert "uptime_seconds" in data
        assert "version" in data
        assert "request_count" in data
        assert isinstance(data["uptime_seconds"], (int, float))
        assert isinstance(data["request_count"], int)
    finally:
        server.shutdown()
