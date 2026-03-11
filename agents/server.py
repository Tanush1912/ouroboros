"""HTTP server with structured logging, /health and /status endpoints.

Designed to be extended by agents when they create application code.
Logs are emitted as structured JSON to stderr for capture by Vector/Docker.
Optionally forwards request logs to LOG_ENDPOINT (e.g. Vector HTTP source).
"""

import json
import os
import sys
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.request import Request, urlopen

_PORT = 8000
_VERSION = "0.1.0"
_START_TIME = time.monotonic()
_REQUEST_COUNT = 0
_LOG_ENDPOINT = os.environ.get("LOG_ENDPOINT", "")


def _structured_log(level: str, event: str, **kwargs: object) -> None:
    """Emit a structured JSON log line to stderr."""
    entry = {
        "timestamp": time.time(),
        "level": level,
        "event": event,
        **kwargs,
    }
    sys.stderr.write(json.dumps(entry) + "\n")
    sys.stderr.flush()

    if _LOG_ENDPOINT:
        try:
            req = Request(
                _LOG_ENDPOINT,
                data=json.dumps(entry).encode(),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            urlopen(req, timeout=2)
        except Exception:
            pass


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        global _REQUEST_COUNT
        _REQUEST_COUNT += 1

        if self.path == "/health":
            self._json_response(200, {"status": "ok"})
        elif self.path == "/status":
            uptime = time.monotonic() - _START_TIME
            self._json_response(
                200,
                {
                    "status": "ok",
                    "uptime_seconds": round(uptime, 2),
                    "version": _VERSION,
                    "request_count": _REQUEST_COUNT,
                },
            )
        else:
            self.send_error(404)

    def _json_response(self, code: int, body: dict) -> None:
        payload = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format: str, *args: object) -> None:
        _structured_log(
            "info",
            "http_request",
            method=self.command,
            path=self.path,
            client=self.client_address[0],
        )


def main() -> None:
    _structured_log("info", "server_start", port=_PORT, version=_VERSION)
    server = HTTPServer(("0.0.0.0", _PORT), _Handler)
    server.serve_forever()


if __name__ == "__main__":
    main()
