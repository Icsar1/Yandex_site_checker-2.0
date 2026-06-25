from __future__ import annotations

import logging

from app.logging_conf import RedactionFilter


def _record(message: str) -> logging.LogRecord:
    return logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg=message,
        args=(),
        exc_info=None,
    )


def test_redaction_filter_masks_api_key_pattern() -> None:
    record = _record("api key y0__xD7zr4UGN30PSCm5r-8FijDrl8D8iaC-gHL5BSf0B25vHSa")

    RedactionFilter().filter(record)

    assert "y0__" not in record.getMessage()
    assert "***" in record.getMessage()


def test_redaction_filter_masks_password_field() -> None:
    record = _record("login attempt")
    record.password = "plain-text-password"

    RedactionFilter().filter(record)

    assert record.password == "***"
