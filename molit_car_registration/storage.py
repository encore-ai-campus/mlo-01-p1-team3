"""누적 CSV를 읽고 병합하고 저장하는 모듈."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from .periods import normalize_month


def load_store(path: Path) -> tuple[list[dict[str, str]], list[str]]:
    if not path.exists():
        return [], []
    with path.open("r", newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        headers = reader.fieldnames or []
        return [dict(row) for row in reader], headers


def row_key(row: dict[str, Any], headers: list[str]) -> tuple[str, ...]:
    # 기준월과 첫 두 지역/분류 컬럼을 행 식별자로 사용합니다.
    identity_headers = headers[:3]
    return tuple(
        "" if row.get(header) is None else str(row.get(header))
        for header in identity_headers
    )


def period_number(row: dict[str, Any]) -> int:
    raw = str(row.get("기준월", "")).replace("-", "")
    try:
        return int(normalize_month(raw))
    except ValueError:
        return -1


def build_headers(
    existing: list[dict[str, Any]],
    incoming: list[dict[str, Any]],
    existing_headers: list[str],
) -> list[str]:
    headers = list(existing_headers) or ["기준월"]
    for row in [*existing, *incoming]:
        for key in row:
            if key not in headers:
                headers.append(key)
    if "기준월" in headers and headers[0] != "기준월":
        headers.remove("기준월")
        headers.insert(0, "기준월")
    return headers


def merge_rows(
    existing: list[dict[str, Any]],
    incoming: list[dict[str, Any]],
    headers: list[str],
) -> list[dict[str, Any]]:
    merged: dict[tuple[str, ...], dict[str, Any]] = {}
    for row in existing:
        merged[row_key(row, headers)] = {header: row.get(header, "") for header in headers}
    for row in incoming:
        merged[row_key(row, headers)] = {header: row.get(header, "") for header in headers}

    return sorted(
        merged.values(),
        key=lambda row: (-period_number(row), row_key(row, headers)),
    )


def write_store(path: Path, rows: list[dict[str, Any]], headers: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
