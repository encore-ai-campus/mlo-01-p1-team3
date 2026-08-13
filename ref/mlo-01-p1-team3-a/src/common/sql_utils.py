"""Small conversions shared by the MySQL-compatible writers."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any


def to_sql_datetime(value: Any) -> Any:
    """Convert ISO strings to MySQL DATETIME text while preserving NULL."""

    if value in (None, "") or isinstance(value, datetime):
        return value
    text = str(value).strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return value
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def to_sql_date(value: Any) -> Any:
    if value in (None, "") or isinstance(value, datetime):
        return value
    text = str(value).strip()
    if len(text) >= 10 and text[4] == "-" and text[7] == "-":
        return text[:10]
    return value


def to_json(value: Any) -> Any:
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
