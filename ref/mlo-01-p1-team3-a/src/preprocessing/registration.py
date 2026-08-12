"""Pure MOLIT registration-report row to normalized SQL-row transformation."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import date
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from common.config import Settings


class RegistrationPreprocessError(ValueError):
    """A registration source row cannot satisfy the normalized data contract."""

    def __init__(self, message: str, code: str = "registration_rejected") -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class RegistrationRejectedRecord:
    index: int
    error_code: str
    sido_name: Optional[str]
    sigungu_name: Optional[str]
    vehicle_type: Optional[str]
    usage_type: Optional[str]


def normalize_period(value: Any) -> str:
    text = re.sub(r"[^0-9]", "", str(value or ""))
    if len(text) != 6:
        raise RegistrationPreprocessError("period must be YYYY-MM", code="invalid_reference_month")
    year, month = int(text[:4]), int(text[4:])
    if not 1 <= month <= 12:
        raise RegistrationPreprocessError("period month is invalid", code="invalid_reference_month")
    return f"{year:04d}{month:02d}"


def _scalar(value: Any) -> Any:
    """Normalize API number strings while preserving a missing measure as NULL."""

    if value is None or value == "":
        return None
    if isinstance(value, str):
        text = value.strip()
        if text in {"-", "–"}:
            return None
        compact = text.replace(",", "")
        if re.fullmatch(r"-?\d+", compact):
            return int(compact)
        return text
    return value


def _normalized_key(value: Any) -> str:
    return re.sub(r"[^0-9a-z가-힣]", "", str(value or "").lower())


def _pick(row: Mapping[str, Any], names: Sequence[str]) -> Any:
    normalized = {_normalized_key(key): value for key, value in row.items()}
    for name in names:
        value = normalized.get(_normalized_key(name))
        if value not in (None, ""):
            return value
    return None


def _reference_month(period: str, row: Mapping[str, Any]) -> str:
    raw = _pick(
        row,
        (
            "월",
            "월일",
            "기준월",
            "date",
            "reference_month",
            "referenceMonth",
            "reference_date",
            "referenceDate",
            "period",
        ),
    )
    if raw in (None, ""):
        raw = period
    digits = re.sub(r"[^0-9]", "", str(raw).strip())
    if len(digits) == 6:
        try:
            return date(int(digits[:4]), int(digits[4:]), 1).isoformat()
        except ValueError as exc:
            raise RegistrationPreprocessError(
                "reference month is invalid", code="invalid_reference_month"
            ) from exc
    if len(digits) == 8:
        try:
            parsed = date(int(digits[:4]), int(digits[4:6]), int(digits[6:]))
        except ValueError as exc:
            raise RegistrationPreprocessError(
                "reference date is invalid", code="invalid_reference_month"
            ) from exc
        return parsed.replace(day=1).isoformat()
    raise RegistrationPreprocessError("reference month is invalid", code="invalid_reference_month")


def _location(row: Mapping[str, Any]) -> Tuple[Optional[str], Optional[str]]:
    sido = _pick(
        row,
        ("시도명", "sido_name", "sidoName", "province", "지역명", "region_name", "regionName"),
    )
    sigungu = _pick(
        row,
        ("시군구", "시군구명", "sigungu", "sigungu_name", "sigunguName", "district"),
    )
    sido_text = str(sido).strip() if sido not in (None, "") else None
    sigungu_text = str(sigungu).strip() if sigungu not in (None, "") else None
    return sido_text, sigungu_text


def _metric_candidates(row: Mapping[str, Any]) -> Iterable[Tuple[str, str, Any]]:
    """Yield every ``차량구분>용도구분`` measure in source order.

    The current API returns twenty keys such as ``승용>관용`` and
    ``총계>계``. A direct three-field shape is retained for fixture adapters
    and future source adapters that already provide normalized dimensions.
    """

    composite: List[Tuple[str, str, Any]] = []
    for key, value in row.items():
        key_text = str(key).strip()
        if ">" not in key_text:
            continue
        vehicle_type, usage_type = (part.strip() for part in key_text.split(">", 1))
        if vehicle_type and usage_type:
            composite.append((vehicle_type, usage_type, value))
    if composite:
        yield from composite
        return

    direct_type = _pick(row, ("차량구분", "차량유형", "차종", "vehicle_type", "vehicleType"))
    direct_usage = _pick(row, ("용도구분", "용도", "usage_type", "usageType", "purpose"))
    direct_quantity = _pick(
        row,
        ("수량", "등록대수", "등록수", "quantity", "registered_count", "registeredCount", "count", "value"),
    )
    if direct_type not in (None, "") and direct_usage not in (None, ""):
        yield str(direct_type).strip(), str(direct_usage).strip(), direct_quantity


def _canonical_hash(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def transform_registration_row(
    raw: Mapping[str, Any], *, period: str, settings: Settings, run_id: str, collected_at: str
) -> List[Dict[str, Any]]:
    """Flatten one API row into one prepared row per vehicle/use measure."""

    normalized_period = normalize_period(period)
    report_month = _reference_month(normalized_period, raw)
    sido_name, sigungu_name = _location(raw)
    if not sido_name:
        raise RegistrationPreprocessError("sido_name is required", code="missing_sido_name")
    if not sigungu_name:
        raise RegistrationPreprocessError("sigungu_name is required", code="missing_sigungu_name")

    candidates = list(_metric_candidates(raw))
    if not candidates:
        raise RegistrationPreprocessError("no registration measure found", code="missing_registration_measure")

    rows: List[Dict[str, Any]] = []
    for vehicle_type, usage_type, raw_quantity in candidates:
        vehicle_type = str(vehicle_type).strip()
        usage_type = str(usage_type).strip()
        if not vehicle_type:
            raise RegistrationPreprocessError("vehicle_type is required", code="missing_vehicle_type")
        if not usage_type:
            raise RegistrationPreprocessError("usage_type is required", code="missing_usage_type")
        quantity = _scalar(raw_quantity)
        if quantity is not None and (
            isinstance(quantity, bool) or not isinstance(quantity, int) or quantity < 0
        ):
            raise RegistrationPreprocessError(
                "quantity must be a non-negative integer", code="invalid_quantity"
            )
        stable = {
            "report_month": report_month,
            "sido_name": sido_name,
            "sigungu_name": sigungu_name,
            "vehicle_type": vehicle_type,
            "usage_type": usage_type,
            "quantity": quantity,
        }
        rows.append(
            {
                **stable,
                "source_name": "molit_car_registration",
                "source_url": settings.registration_api_url,
                "run_id": run_id,
                "collected_at": collected_at,
                "created_at": collected_at,
                "updated_at": collected_at,
                "content_hash": _canonical_hash(stable),
            }
        )
    return rows


def transform_registration_records(
    records: Iterable[Mapping[str, Any]], *, period: str, settings: Settings, run_id: str, collected_at: str
) -> Tuple[List[Dict[str, Any]], List[RegistrationRejectedRecord]]:
    valid: List[Dict[str, Any]] = []
    rejected: List[RegistrationRejectedRecord] = []
    for index, raw in enumerate(records):
        try:
            valid.extend(
                transform_registration_row(
                    raw, period=period, settings=settings, run_id=run_id, collected_at=collected_at
                )
            )
        except RegistrationPreprocessError as exc:
            sido_name, sigungu_name = _location(raw)
            rejected.append(
                RegistrationRejectedRecord(
                    index=index,
                    error_code=exc.code,
                    sido_name=sido_name,
                    sigungu_name=sigungu_name,
                    vehicle_type=None,
                    usage_type=None,
                )
            )
    return valid, rejected
