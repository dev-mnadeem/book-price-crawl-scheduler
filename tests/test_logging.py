from __future__ import annotations

import logging

import orjson

from app.config.logging import ORJSONFormatter


def _format(**extra) -> dict:
    record = logging.makeLogRecord({"name": "crawler", "levelname": "INFO", "msg": "Crawl completed", **extra})
    return orjson.loads(ORJSONFormatter().format(record))


def test_extra_fields_reach_the_log_line():
    line = _format(inserted=3, updated=1, unchanged=990, failed=0)
    assert line["message"] == "Crawl completed"
    assert (line["inserted"], line["updated"], line["unchanged"], line["failed"]) == (3, 1, 990, 0)


def test_standard_record_attributes_are_not_repeated():
    line = _format()
    assert "args" not in line and "msecs" not in line and "pathname" not in line


def test_values_orjson_cannot_encode_fall_back_to_str():
    from pathlib import Path

    assert _format(report=Path("reports/2026-01-01.json"))["report"] == "reports/2026-01-01.json"
