from __future__ import annotations

import logging
import os
from logging import Handler, LogRecord
from pathlib import Path
from typing import Any, Dict

import orjson

from app.config.settings import settings


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
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return orjson.dumps(payload).decode()


def setup_logging(level: str | None = None) -> None:
    log_level = (level or settings.log_level).upper()

    # Ensure log directory exists
    Path(settings.logs_dir).mkdir(parents=True, exist_ok=True)

    root = logging.getLogger()
    root.setLevel(log_level)

    # Clear existing handlers to avoid duplicate logs on reload
    for h in list(root.handlers):
        root.removeHandler(h)

    console = logging.StreamHandler()
    console.setLevel(log_level)
    console.setFormatter(ORJSONFormatter())

    file_handler = logging.FileHandler(Path(settings.logs_dir) / "app.log")
    file_handler.setLevel(log_level)
    file_handler.setFormatter(ORJSONFormatter())

    root.addHandler(console)
    root.addHandler(file_handler)

    # Reduce noise from libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("apscheduler").setLevel(logging.INFO)
