"""HTTP server with structured logging, /health and /status endpoints.

Designed to be extended by agents when they create application code.
Uses the shared VectorHandler logger from agents/tools/app_logging.py.
"""

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

from agents.tools.app_logging import get_logger

_PORT = 8000
_VERSION = "0.1.0"
_START_TIME = time.monotonic()
_REQUEST_COUNT = 0
_REQUEST_COUNT_LOCK = threading.Lock()
_logger = get_logger("server")


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        global _REQUEST_COUNT
        with _REQUEST_COUNT_LOCK:
            _REQUEST_COUNT += 1
            count = _REQUEST_COUNT

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
                    "request_count": count,
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
        import contextlib

        with contextlib.suppress(Exception):
            _logger.info(
                "http_request method=%s path=%s client=%s",
                self.command,
                self.path,
                self.client_address[0],
            )


def main() -> None:
    _logger.info("server_start port=%d version=%s", _PORT, _VERSION)
    server = HTTPServer(("0.0.0.0", _PORT), _Handler)
    server.serve_forever()


if __name__ == "__main__":
    main()
