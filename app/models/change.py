from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class FieldDiff(BaseModel):
    field: str
    old: Any | None
    new: Any | None


class ChangeLog(BaseModel):
    book_upc: str
    change_type: Literal["new", "update"]
    changes: list[FieldDiff] = Field(default_factory=list)
    timestamp: datetime

    # Assessed at write time rather than on read: the severity describes what
    # the thresholds said when the change was detected. Recomputing it later
    # would silently reclassify history whenever a threshold was tuned.
    severity: Literal["critical", "notable", "minor", "cosmetic"] | None = None
    reasons: list[str] = Field(default_factory=list)
    signals: dict[str, Any] = Field(default_factory=dict)


class ChangesResponse(BaseModel):
    items: list[ChangeLog]
    count: int
