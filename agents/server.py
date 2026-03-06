"""Minimal HTTP server exposing /health for container liveness checks."""

import json
from http.server import BaseHTTPRequestHandler, HTTPServer

_PORT = 8000


class _HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path == "/health":
            body = json.dumps({"status": "ok"}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_error(404)

    def log_message(self, format: str, *args: object) -> None:
        pass  # silence per-request logs


def main() -> None:
    server = HTTPServer(("0.0.0.0", _PORT), _HealthHandler)
    server.serve_forever()


if __name__ == "__main__":
    main()
