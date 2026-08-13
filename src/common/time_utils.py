"""Shared UTC time formatting and conversion for operational timestamps."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Optional


UTC = timezone.utc


def utc_now() -> datetime:
    """Return the current timezone-aware UTC datetime without microseconds."""

    return datetime.now(UTC).replace(microsecond=0)


def format_utc_datetime(value: Any, *, required: bool = False) -> Optional[str]:
    """Normalize a datetime-like value to canonical UTC ISO 8601 text.

    The canonical output is ``YYYY-MM-DDTHH:MM:SS+00:00``.  A naive
    ``datetime`` or ISO string is interpreted as UTC.  Date-only values are
    interpreted as UTC midnight.  ``None`` and an empty string are preserved
    as ``None`` unless ``required`` is true.
    """

    if value is None or value == "":
        if required:
            raise ValueError("datetime value is required")
        return None

    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, date):
        parsed = datetime.combine(value, datetime.min.time())
    elif isinstance(value, str):
        text = value.strip()
        if not text:
            if required:
                raise ValueError("datetime value is required")
            return None
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("datetime value must be ISO 8601") from exc
    else:
        raise TypeError("datetime value must be date, datetime, ISO text, or None")

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC).replace(microsecond=0).isoformat()


def to_utc_datetime(value: Any, *, required: bool = False) -> Optional[datetime]:
    """Normalize a datetime-like value to a timezone-aware UTC ``datetime``.

    ``format_utc_datetime`` remains the string formatter for stage, JSONL,
    and SQL boundaries.  Repository adapters that need a native datetime
    value, such as MongoDB BSON Date writes, should use this helper instead.
    """

    normalized = format_utc_datetime(value, required=required)
    if normalized is None:
        return None
    parsed = datetime.fromisoformat(normalized)
    assert parsed.tzinfo is not None
    return parsed


def format_utc_date(value: Any, *, required: bool = False) -> Optional[str]:
    """Normalize a date-like value to canonical ``YYYY-MM-DD`` text.

    Datetime and ISO datetime values are converted to UTC before taking the
    calendar date.  Date-only values retain their date.  ``None`` and an
    empty string are preserved as ``None`` unless ``required`` is true.
    """

    if value is None or value == "":
        if required:
            raise ValueError("date value is required")
        return None

    if isinstance(value, datetime):
        normalized_datetime = format_utc_datetime(value, required=True)
        assert normalized_datetime is not None
        return normalized_datetime[:10]
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, str):
        text = value.strip()
        if not text:
            if required:
                raise ValueError("date value is required")
            return None
        try:
            if "T" in text or " " in text:
                normalized_datetime = format_utc_datetime(text, required=True)
                assert normalized_datetime is not None
                return normalized_datetime[:10]
            return date.fromisoformat(text).isoformat()
        except ValueError as exc:
            raise ValueError("date value must be ISO date or datetime") from exc

    raise TypeError("date value must be date, datetime, ISO text, or None")


def utc_now_iso() -> str:
    """Return the current UTC datetime in canonical ISO 8601 text."""

    result = format_utc_datetime(utc_now(), required=True)
    assert result is not None
    return result


__all__ = [
    "UTC",
    "format_utc_date",
    "format_utc_datetime",
    "to_utc_datetime",
    "utc_now",
    "utc_now_iso",
]
