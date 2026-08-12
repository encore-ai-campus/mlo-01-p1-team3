"""Small database-neutral conversions used by MySQL-compatible sinks."""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from typing import Any


def to_sql_datetime(value: Any) -> Any:
    """Convert an ISO datetime to UTC MySQL DATETIME text; preserve NULL."""

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
    """Convert ISO date/datetime text to a MySQL DATE value representation."""

    if value in (None, "") or isinstance(value, (date, datetime)):
        return value
    text = str(value).strip()
    if len(text) >= 10 and text[4] == "-" and text[7] == "-":
        return text[:10]
    return value


def to_json(value: Any) -> Optional[str]:
    return None if value is None else json.dumps(value, ensure_ascii=False, separators=(",", ":"))


__all__ = ["to_json", "to_sql_date", "to_sql_datetime"]
