"""Structured logging for agent-written applications.

Provides a drop-in logger that sends structured JSON to Vector's HTTP
source ($LOG_ENDPOINT) and to stderr (for Docker/CI log capture).

Usage in agent-written code::

    from agents.tools.app_logging import get_logger

    logger = get_logger("my-service")
    logger.info("request handled, path=/api/data status=200")

Vector expects JSON with ``timestamp``, ``service``, and ``level`` fields.
This handler produces exactly that format. Stdlib-only — no external deps.
"""

import json
import logging
import os
import sys
import time
from urllib.request import Request, urlopen


class VectorHandler(logging.Handler):
    """Logging handler that forwards structured JSON to Vector and stderr."""

    def __init__(self, service: str) -> None:
        super().__init__()
        self.service = service

    def emit(self, record: logging.LogRecord) -> None:
        entry = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "service": self.service,
            "level": record.levelname.lower(),
            "message": record.getMessage(),
        }
        # Always write to stderr (captured by Docker/CI)
        sys.stderr.write(json.dumps(entry) + "\n")
        sys.stderr.flush()

        # Forward to Vector if LOG_ENDPOINT is configured
        log_endpoint = os.environ.get("LOG_ENDPOINT", "")
        if log_endpoint:
            try:
                req = Request(
                    log_endpoint,
                    data=json.dumps(entry).encode(),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                urlopen(req, timeout=2)
            except Exception as exc:
                sys.stderr.write(f"log_forward_failed: {exc}\n")


def get_logger(service: str) -> logging.Logger:
    """Return a logger that sends structured JSON to Vector and stderr.

    Safe to call multiple times with the same service name — handlers
    are only added once.
    """
    logger = logging.getLogger(f"ouroboros.{service}")
    if not logger.handlers:
        logger.addHandler(VectorHandler(service))
        logger.setLevel(logging.DEBUG)
    return logger
