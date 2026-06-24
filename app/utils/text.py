from __future__ import annotations

import re
from typing import Optional

SPACE_RE = re.compile(r"\s+")


def normalize_text(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    return SPACE_RE.sub(" ", value.strip())


def normalize_category(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    s = normalize_text(value) or ""
    return s.lower() or None
