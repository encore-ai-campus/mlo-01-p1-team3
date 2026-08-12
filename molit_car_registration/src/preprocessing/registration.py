"""자동차등록 원본 행을 정규화된 업무 행으로 변환합니다."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import date
from typing import Any, Iterable, Mapping, Optional

from common.config import Settings


class RegistrationPreprocessError(ValueError):
    def __init__(self, message: str, code: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class RegistrationRejectedRecord:
    index: int
    error_code: str
    sido_name: Optional[str]
    sigungu_name: Optional[str]


def _normalized_key(value: Any) -> str:
    return re.sub(r"[^0-9a-z가-힣]", "", str(value or "").lower())


def _pick(row: Mapping[str, Any], names: tuple[str, ...]) -> Any:
    values = {_normalized_key(key): value for key, value in row.items()}
    for name in names:
        value = values.get(_normalized_key(name))
        if value not in (None, ""):
            return value
    return None


def _scalar(value: Any) -> Any:
    if value in (None, ""):
        return None
    if isinstance(value, str):
        value = value.strip()
        if value in {"-", "–"}:
            return None
        compact = value.replace(",", "")
        if re.fullmatch(r"-?\d+", compact):
            return int(compact)
        return value
    return value


def _month(period: str, row: Mapping[str, Any]) -> str:
    raw = _pick(row, ("기준월", "월", "date", "period")) or period
    digits = re.sub(r"[^0-9]", "", str(raw))
    if len(digits) == 6:
        year, month = int(digits[:4]), int(digits[4:])
        try:
            return date(year, month, 1).isoformat()
        except ValueError as exc:
            raise RegistrationPreprocessError("invalid reference month", "invalid_reference_month") from exc
    raise RegistrationPreprocessError("invalid reference month", "invalid_reference_month")


def _location(row: Mapping[str, Any]) -> tuple[Optional[str], Optional[str]]:
    sido = _pick(row, ("시도명", "sido_name", "sidoName", "province", "지역명"))
    sigungu = _pick(row, ("시군구", "시군구명", "sigungu_name", "sigunguName", "district"))
    return (
        str(sido).strip() if sido not in (None, "") else None,
        str(sigungu).strip() if sigungu not in (None, "") else None,
    )


def _metrics(row: Mapping[str, Any]) -> Iterable[tuple[str, str, Any]]:
    for key, value in row.items():
        if ">" in str(key):
            vehicle_type, usage_type = (part.strip() for part in str(key).split(">", 1))
            if vehicle_type and usage_type:
                yield vehicle_type, usage_type, value


def _hash(value: Mapping[str, Any]) -> str:
    text = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def transform_row(raw: Mapping[str, Any], *, period: str, settings: Settings, run_id: str, collected_at: str) -> list[dict[str, Any]]:
    report_month = _month(period, raw)
    sido_name, sigungu_name = _location(raw)
    if not sido_name:
        raise RegistrationPreprocessError("sido_name is required", "missing_sido_name")
    if not sigungu_name:
        raise RegistrationPreprocessError("sigungu_name is required", "missing_sigungu_name")

    candidates = list(_metrics(raw))
    if not candidates:
        raise RegistrationPreprocessError("registration measure is missing", "missing_measure")

    result = []
    for vehicle_type, usage_type, raw_quantity in candidates:
        quantity = _scalar(raw_quantity)
        if quantity is not None and (not isinstance(quantity, int) or quantity < 0):
            raise RegistrationPreprocessError("quantity must be non-negative integer", "invalid_quantity")
        stable = {
            "report_month": report_month,
            "sido_name": sido_name,
            "sigungu_name": sigungu_name,
            "vehicle_type": vehicle_type,
            "usage_type": usage_type,
            "quantity": quantity,
        }
        result.append(
            {
                **stable,
                "source_name": "molit_car_registration",
                "source_url": settings.registration_api_url,
                "run_id": run_id,
                "collected_at": collected_at,
                "content_hash": _hash(stable),
            }
        )
    return result


def transform_records(records: Iterable[Mapping[str, Any]], *, period: str, settings: Settings, run_id: str, collected_at: str) -> tuple[list[dict[str, Any]], list[RegistrationRejectedRecord]]:
    valid: list[dict[str, Any]] = []
    rejected: list[RegistrationRejectedRecord] = []
    for index, raw in enumerate(records):
        try:
            valid.extend(transform_row(raw, period=period, settings=settings, run_id=run_id, collected_at=collected_at))
        except RegistrationPreprocessError as exc:
            sido_name, sigungu_name = _location(raw)
            rejected.append(RegistrationRejectedRecord(index, exc.code, sido_name, sigungu_name))
    return valid, rejected
