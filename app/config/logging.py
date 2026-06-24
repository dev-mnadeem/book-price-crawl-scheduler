from __future__ import annotations

import logging
from logging import LogRecord
from pathlib import Path
from typing import Any, Dict

import orjson

from app.config.settings import settings

# Attributes every LogRecord has; anything else on the record came from extra=.
_RECORD_FIELDS = set(vars(logging.makeLogRecord({}))) | {"message", "asctime", "taskName"}


class ORJSONFormatter(logging.Formatter):
    def format(self, record: LogRecord) -> str:
        payload: Dict[str, Any] = {
            "level": record.levelname,
            "time": self.formatTime(record, datefmt="%Y-%m-%dT%H:%M:%S%z"),
            "name": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "func": record.funcName,
            "line": record.lineno,
        }
        for key, value in vars(record).items():
            if key not in _RECORD_FIELDS and key not in payload:
                payload[key] = value
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return orjson.dumps(payload, default=str).decode()


def setup_logging(level: str | None = None) -> None:
    log_level = (level or settings.log_level).upper()
    Path(settings.logs_dir).mkdir(parents=True, exist_ok=True)

    root = logging.getLogger()
    root.setLevel(log_level)

    # uvicorn --reload calls this again in the same process.
    for h in list(root.handlers):
        root.removeHandler(h)

    formatter = ORJSONFormatter()
    for handler in (logging.StreamHandler(), logging.FileHandler(Path(settings.logs_dir) / "app.log")):
        handler.setLevel(log_level)
        handler.setFormatter(formatter)
        root.addHandler(handler)

    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("apscheduler").setLevel(logging.INFO)
