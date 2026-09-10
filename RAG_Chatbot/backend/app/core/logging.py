"""Minimal JSON logging with a request-scoped correlation identifier."""

from __future__ import annotations

import json
import logging
import sys
from contextvars import ContextVar
from datetime import datetime, timezone


request_id_context: ContextVar[str | None] = ContextVar("request_id", default=None)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        request_id = request_id_context.get()
        if request_id:
            payload["request_id"] = request_id
        # This allowlist intentionally excludes request bodies, credentials, tool arguments,
        # provider payloads, and retrieved text while retaining safe operational audit data.
        for field in (
            "endpoint", "method", "status", "latency_ms", "conversation_id", "employee_id",
            "tool_name", "tool_category", "result_status", "duration_ms", "error_code",
            "pending_action_id", "tool_error_code",
        ):
            value = getattr(record, field, None)
            if value is not None:
                payload[field] = value
        return json.dumps(payload, default=str)


def configure_logging(level: str = "INFO") -> None:
    """Configure logs without serializing settings or request bodies."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level.upper())
