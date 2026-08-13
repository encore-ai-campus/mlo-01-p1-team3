"""
===============================================================================
[TEST START] common.sql_utils unit tests

Purpose:
    Verify UTC SQL datetime/date conversion and compact JSON serialization.
===============================================================================
"""

from __future__ import annotations

import sys
from datetime import date, datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for import_path in (str(ROOT), str(SRC)):
    if import_path not in sys.path:
        sys.path.insert(0, import_path)

from common.sql_utils import to_json, to_sql_date, to_sql_datetime  # noqa: E402


def test_common_sql_utils_converts_utc_dates_times_and_json() -> None:
    """Check null preservation, timezone conversion, and JSON formatting."""

    assert to_sql_datetime(None) is None
    assert to_sql_datetime("") == ""
    assert to_sql_datetime("2026-08-12T12:34:56+09:00") == "2026-08-12 03:34:56"
    assert to_sql_datetime(datetime(2026, 8, 12, 12, 34, 56)) == "2026-08-12 12:34:56"
    assert to_sql_date("2026-08-12T00:30:00+09:00") == "2026-08-11"
    assert to_sql_date(date(2026, 8, 12)) == date(2026, 8, 12)
    assert to_sql_date("not-a-date") == "not-a-date"
    assert to_json({"한글": 1}) == '{"한글":1}'


"""
===============================================================================
[TEST END] common.sql_utils unit tests
===============================================================================
"""
