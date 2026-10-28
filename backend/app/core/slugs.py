from __future__ import annotations

import re

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify(value: str, fallback: str = "item") -> str:
    slug = _SLUG_RE.sub("-", (value or "").lower()).strip("-")
    return slug or fallback
