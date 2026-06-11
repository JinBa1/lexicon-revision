from __future__ import annotations

import json
import logging

from src.worker.logging import JsonLogFormatter


def test_formats_record_as_json_with_extras() -> None:
    formatter = JsonLogFormatter()
    record = logging.LogRecord(
        name="src.worker.handler",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="ingest job started",
        args=(),
        exc_info=None,
    )
    record.job_id = "j-1"

    payload = json.loads(formatter.format(record))

    assert payload["message"] == "ingest job started"
    assert payload["level"] == "INFO"
    assert payload["logger"] == "src.worker.handler"
    assert payload["job_id"] == "j-1"
    assert "timestamp" in payload
