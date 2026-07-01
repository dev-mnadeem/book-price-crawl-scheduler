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


class ChangesResponse(BaseModel):
    items: list[ChangeLog]
    count: int
