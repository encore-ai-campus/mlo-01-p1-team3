from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from common import UTC, format_utc_date, format_utc_datetime, utc_now, utc_now_iso


def test_format_utc_datetime_normalizes_timezone_and_removes_microseconds() -> None:
    assert format_utc_datetime("2026-02-01T09:00:00.987654+09:00") == "2026-02-01T00:00:00+00:00"
    assert format_utc_datetime("2026-02-01T00:00:00Z") == "2026-02-01T00:00:00+00:00"
    assert format_utc_datetime("2026-02-01T00:00:00") == "2026-02-01T00:00:00+00:00"


def test_format_utc_datetime_accepts_python_date_types_and_empty_values() -> None:
    aware = datetime(2026, 2, 1, 9, 0, 0, 123456, tzinfo=timezone(timedelta(hours=9)))

    assert format_utc_datetime(aware) == "2026-02-01T00:00:00+00:00"
    assert format_utc_datetime(date(2026, 2, 1)) == "2026-02-01T00:00:00+00:00"
    assert format_utc_datetime(None) is None
    assert format_utc_datetime("   ") is None


def test_format_utc_datetime_rejects_invalid_required_values() -> None:
    with pytest.raises(ValueError, match="ISO 8601"):
        format_utc_datetime("2026/02/01")
    with pytest.raises(ValueError, match="required"):
        format_utc_datetime(None, required=True)
    with pytest.raises(TypeError, match="date, datetime"):
        format_utc_datetime(20260201)


def test_format_utc_date_returns_date_without_time() -> None:
    assert format_utc_date("2026-02-01") == "2026-02-01"
    assert format_utc_date("2026-02-01T00:00:00Z") == "2026-02-01"
    assert format_utc_date("2026-02-01T00:30:00+09:00") == "2026-01-31"
    assert format_utc_date(datetime(2026, 2, 1, 9, tzinfo=timezone(timedelta(hours=9)))) == "2026-02-01"
    assert format_utc_date(None) is None


def test_format_utc_date_rejects_invalid_values() -> None:
    with pytest.raises(ValueError, match="ISO date or datetime"):
        format_utc_date("2026-02-31")
    with pytest.raises(ValueError, match="required"):
        format_utc_date("", required=True)
    with pytest.raises(TypeError, match="date, datetime"):
        format_utc_date(20260201)


def test_utc_now_helpers_return_timezone_aware_second_precision_values() -> None:
    now = utc_now()
    iso = utc_now_iso()

    assert now.tzinfo == UTC
    assert now.microsecond == 0
    assert iso.endswith("+00:00")
    assert "." not in iso
