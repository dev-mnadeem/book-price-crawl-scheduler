from __future__ import annotations

import re
from typing import Optional

SPACE_RE = re.compile(r"\s+")
NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")


def normalize_text(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    return SPACE_RE.sub(" ", value.strip())


def normalize_category(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    s = normalize_text(value) or ""
    return s.lower() or None


def slugify_category(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    s = (normalize_text(value) or "").lower()
    s = NON_ALNUM_RE.sub("-", s).strip("-")
    return s or None
