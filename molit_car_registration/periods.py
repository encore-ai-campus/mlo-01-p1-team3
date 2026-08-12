"""월 기간을 계산하고 검증하는 함수."""

from __future__ import annotations

import re
from datetime import datetime


def normalize_month(raw: str) -> str:
    compact = re.sub(r"[^0-9]", "", raw)
    if len(compact) != 6:
        raise ValueError("월은 YYYY-MM 또는 YYYYMM 형식이어야 합니다.")
    year, month = int(compact[:4]), int(compact[4:])
    if not 1 <= month <= 12:
        raise ValueError("월은 01부터 12 사이여야 합니다.")
    return f"{year:04d}{month:02d}"


def month_label(period: str) -> str:
    period = normalize_month(period)
    return f"{period[:4]}-{period[4:]}"


def add_month(period: str, offset: int) -> str:
    period = normalize_month(period)
    year, month = int(period[:4]), int(period[4:])
    serial = year * 12 + (month - 1) + offset
    new_year, zero_based_month = divmod(serial, 12)
    return f"{new_year:04d}{zero_based_month + 1:02d}"


def month_distance(start_period: str, end_period: str) -> int:
    start = normalize_month(start_period)
    end = normalize_month(end_period)
    start_year, start_month = int(start[:4]), int(start[4:])
    end_year, end_month = int(end[:4]), int(end[4:])
    return (end_year * 12 + end_month) - (start_year * 12 + start_month)


def current_period() -> str:
    return datetime.now().strftime("%Y%m")
