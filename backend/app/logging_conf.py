from __future__ import annotations

import json
import logging
import re
import sys
from datetime import UTC, datetime
from typing import Any


SENSITIVE_FIELD_MARKERS = (
    "key",
    "password",
    "secret",
    "token",
    "cookie",
    "authorization",
)

API_KEY_PATTERN = re.compile(
    r"y0_[A-Za-z0-9_-]+|AQVN[A-Za-z0-9_-]+|(?<![A-Za-z0-9_-])[A-Za-z0-9_-]{21,}(?![A-Za-z0-9_-])"
)

STANDARD_LOG_RECORD_ATTRS = set(logging.makeLogRecord({}).__dict__) | {
    "asctime",
    "message",
}


def _is_sensitive_field(name: str) -> bool:
    lowered = name.lower()
    return any(marker in lowered for marker in SENSITIVE_FIELD_MARKERS)


def redact_value(value: Any, field_name: str | None = None) -> Any:
    if field_name and _is_sensitive_field(field_name):
        return "***"

    if isinstance(value, str):
        return API_KEY_PATTERN.sub("***", value)

    if isinstance(value, dict):
        return {key: redact_value(item, str(key)) for key, item in value.items()}

    if isinstance(value, tuple):
        return tuple(redact_value(item) for item in value)

    if isinstance(value, list):
        return [redact_value(item) for item in value]

    if isinstance(value, set):
        return {redact_value(item) for item in value}

    return value


class RedactionFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact_value(record.msg)
        if record.args:
            record.args = redact_value(record.args)

        for field_name, value in list(record.__dict__.items()):
            if field_name in STANDARD_LOG_RECORD_ATTRS:
                continue
            setattr(record, field_name, redact_value(value, field_name))

        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)

        for field_name, value in record.__dict__.items():
            if field_name in STANDARD_LOG_RECORD_ATTRS or field_name in payload:
                continue
            payload[field_name] = redact_value(value, field_name)

        return json.dumps(payload, ensure_ascii=False, default=str)


def setup_logging(level: str = "INFO") -> None:
    numeric_level = getattr(logging, level.upper(), logging.INFO)
    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)
    root_logger.handlers.clear()

    redaction_filter = RedactionFilter()
    root_logger.filters = [
        existing
        for existing in root_logger.filters
        if not isinstance(existing, RedactionFilter)
    ]
    root_logger.addFilter(redaction_filter)

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(numeric_level)
    handler.setFormatter(JsonFormatter())
    handler.addFilter(redaction_filter)
    root_logger.addHandler(handler)
