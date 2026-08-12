"""Transform the used-car API object into the V001 relational contract.

The collector owns transport and pagination.  This module only understands the
documented source object and emits one prepared aggregate per listing.  The
loader decides how that aggregate is written to the normalized SQL tables.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

from common.config import Settings
from common.time_utils import format_utc_date, format_utc_datetime, utc_now_iso


class PreprocessError(ValueError):
    """A source record cannot satisfy the SQL data contract."""

    def __init__(self, message: str, code: str = "record_rejected") -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class RejectedRecord:
    index: int
    error_code: str
    record_id: Optional[str]


def _int_value(value: Any, field: str, *, required: bool = False) -> Optional[int]:
    if value in (None, ""):
        if required:
            raise PreprocessError(f"{field} is required", code=f"missing_{field}")
        return None
    if isinstance(value, bool):
        raise PreprocessError(f"{field} must be numeric", code=f"invalid_{field}")
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str):
        compact = value.replace(",", "").strip()
        if re.fullmatch(r"-?\d+", compact):
            return int(compact)
    raise PreprocessError(f"{field} must be an integer", code=f"invalid_{field}")


def _text_value(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _object_value(value: Any, field: str) -> Optional[Mapping[str, Any]]:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise PreprocessError(f"{field} must be an object", code=f"invalid_{field}")
    return value


def _nested_text(value: Optional[Mapping[str, Any]], *keys: str) -> Optional[str]:
    if value is None:
        return None
    for key in keys:
        result = _text_value(value.get(key))
        if result:
            return result
    return None


def _nested_required_id(value: Optional[Mapping[str, Any]], field: str) -> Optional[int]:
    if value is None:
        return None
    return _int_value(value.get("id"), field, required=True)


def _nested_required_text(value: Optional[Mapping[str, Any]], key: str, field: str) -> Optional[str]:
    if value is None:
        return None
    result = _text_value(value.get(key))
    if result is None:
        raise PreprocessError(f"{field} is required", code=f"missing_{field}")
    return result


def _nonnegative_int(value: Any, field: str) -> Optional[int]:
    number = _int_value(value, field)
    if number is not None and number < 0:
        raise PreprocessError(f"{field} must be non-negative", code=f"invalid_{field}")
    return number


def _iso_value(value: Any, field: str) -> Optional[str]:
    text = _text_value(value)
    if text is None:
        return None
    try:
        return format_utc_datetime(text, required=True)
    except (TypeError, ValueError) as exc:
        raise PreprocessError(f"{field} must be ISO 8601", code=f"invalid_{field}") from exc


def _date_value(value: Any, field: str) -> Optional[str]:
    text = _text_value(value)
    if text is None:
        return None
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        raise PreprocessError(f"{field} must be YYYY-MM-DD", code=f"invalid_{field}")
    try:
        normalized = format_utc_date(text, required=True)
    except (TypeError, ValueError) as exc:
        raise PreprocessError(f"{field} must be YYYY-MM-DD", code=f"invalid_{field}") from exc
    assert normalized is not None
    return normalized


def _canonical_hash(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _record_id(record: Mapping[str, Any]) -> Optional[str]:
    raw_id = record.get("id")
    raw_listing = record.get("listingNumber")
    if raw_id not in (None, ""):
        return str(raw_id)
    if raw_listing not in (None, ""):
        return str(raw_listing)
    return None


def _change_record(record: Mapping[str, Any]) -> Mapping[str, Any]:
    """Unwrap common changes-envelope shapes without losing the event ID."""

    for key in ("record", "vehicle", "car", "payload", "entity"):
        candidate = record.get(key)
        if isinstance(candidate, Mapping):
            merged = dict(candidate)
            if "seq" in record:
                merged.setdefault("_change_seq", record["seq"])
            if "eventId" in record:
                merged.setdefault("_event_id", record["eventId"])
            return merged
    nested_data = record.get("data")
    if isinstance(nested_data, Mapping) and ("id" in nested_data or "listingNumber" in nested_data):
        merged = dict(nested_data)
        if "seq" in record:
            merged.setdefault("_change_seq", record["seq"])
        if "eventId" in record:
            merged.setdefault("_event_id", record["eventId"])
        return merged
    return record


def _entity_metadata(*, source_updated_at: Optional[str], run_id: str, collected_at: str, now: str) -> Dict[str, Any]:
    return {
        "source_updated_at": source_updated_at,
        "run_id": run_id,
        "collected_at": collected_at,
        "created_at": now,
        "updated_at": now,
    }


def transform_record(
    record: Mapping[str, Any], *, base_url: str, run_id: str, collected_at: str, dataset_epoch: Optional[str]
) -> Dict[str, Any]:
    """Convert one documented API object into a normalized prepared aggregate.

    The returned mapping has one ``listing`` object and up to five referenced
    entity objects. The listing reaches its brand through ``model.brand_id``;
    a business-area parent is nested under ``business_area.parent``. This is
    the stable stage contract; SQL table ordering, transaction handling, and
    upsert policy stay in ``loading.usedcar``.
    """

    try:
        normalized_collected_at = format_utc_datetime(collected_at, required=True)
    except (TypeError, ValueError) as exc:
        raise PreprocessError("collected_at must be ISO 8601", code="invalid_collected_at") from exc
    assert normalized_collected_at is not None

    source_id = _record_id(record)
    if source_id is None:
        raise PreprocessError("id or listingNumber is required", code="missing_listing_id")

    brand = _object_value(record.get("brand"), "brand")
    model = _object_value(record.get("model"), "model")
    location = _object_value(record.get("location"), "location")
    dealer = _object_value(record.get("dealer"), "dealer")
    business_area = _object_value(record.get("businessArea"), "business_area")
    parent_area = _object_value(business_area.get("parent") if business_area else None, "business_area_parent")

    brand_id = _nested_required_id(brand, "brand_id")
    model_id = _nested_required_id(model, "model_id")
    location_id = _nested_required_id(location, "location_id")
    business_area_id = _nested_required_text(business_area, "id", "business_area_id")
    parent_area_id = _nested_required_text(parent_area, "id", "parent_business_area_id")
    dealer_code = _nested_required_text(dealer, "code", "dealer_code")

    price = record.get("price")
    if isinstance(price, Mapping):
        price = price.get("amount", price.get("value"))

    source_status = _text_value(record.get("status"))
    if source_status is not None:
        source_status = source_status.upper()
        if source_status not in {"AVAILABLE", "RESERVED", "SOLD"}:
            raise PreprocessError("status is outside documented enum", code="invalid_status")

    model_year = _nonnegative_int(record.get("modelYear"), "model_year")
    mileage_km = _nonnegative_int(record.get("mileageKm"), "mileage_km")
    price_krw = _nonnegative_int(price, "price_krw")
    source_created_at = _iso_value(record.get("createdAt"), "created_at")
    source_updated_at = _iso_value(record.get("updatedAt"), "source_updated_at")
    now = utc_now_iso()

    brand_entity = None
    if brand is not None:
        brand_entity = {
            "brand_id": brand_id,
            "name": _nested_text(brand, "name"),
            "slug": _nested_text(brand, "slug"),
            "country": _nested_text(brand, "country"),
            **_entity_metadata(
                source_updated_at=source_updated_at, run_id=run_id, collected_at=normalized_collected_at, now=now
            ),
        }

    model_entity = None
    if model is not None:
        model_entity = {
            "model_id": model_id,
            "brand_id": brand_id,
            "name": _nested_text(model, "name"),
            "slug": _nested_text(model, "slug"),
            "body_type": _nested_text(model, "bodyType", "vehicleType"),
            **_entity_metadata(
                source_updated_at=source_updated_at, run_id=run_id, collected_at=normalized_collected_at, now=now
            ),
        }

    location_entity = None
    if location is not None:
        location_entity = {
            "location_id": location_id,
            "province": _nested_text(location, "province", "sido"),
            "city": _nested_text(location, "city"),
            "sigungu": _nested_text(location, "sigungu", "district"),
            "slug": _nested_text(location, "slug"),
            **_entity_metadata(
                source_updated_at=source_updated_at, run_id=run_id, collected_at=normalized_collected_at, now=now
            ),
        }

    dealer_entity = None
    if dealer is not None:
        dealer_entity = {
            "dealer_code": dealer_code,
            "display_name": _nested_text(dealer, "displayName", "name"),
            "department": _nested_text(dealer, "department"),
            "position": _nested_text(dealer, "position"),
            **_entity_metadata(
                source_updated_at=source_updated_at, run_id=run_id, collected_at=normalized_collected_at, now=now
            ),
        }

    business_area_entity = None
    if business_area is not None:
        business_area_entity = {
            "business_area_id": business_area_id,
            "name": _nested_text(business_area, "name"),
            "slug": _nested_text(business_area, "slug"),
            "parent_business_area_id": parent_area_id,
            "parent": (
                {
                    "business_area_id": parent_area_id,
                    "name": _nested_text(parent_area, "name"),
                    "slug": _nested_text(parent_area, "slug"),
                }
                if parent_area_id is not None
                else None
            ),
            **_entity_metadata(
                source_updated_at=source_updated_at, run_id=run_id, collected_at=normalized_collected_at, now=now
            ),
        }

    stable_content = {
        "listing_id": source_id,
        "listing_number": _text_value(record.get("listingNumber")),
        "title": _text_value(record.get("title")),
        "description": _text_value(record.get("description")),
        "trim": _text_value(record.get("trim")),
        "brand": {
            key: brand_entity.get(key) for key in ("brand_id", "name", "slug", "country")
        } if brand_entity else None,
        "model": {
            key: model_entity.get(key) for key in ("model_id", "brand_id", "name", "slug", "body_type")
        } if model_entity else None,
        "location": {
            key: location_entity.get(key) for key in ("location_id", "province", "city", "sigungu", "slug")
        } if location_entity else None,
        "dealer": {
            key: dealer_entity.get(key) for key in ("dealer_code", "display_name", "department", "position")
        } if dealer_entity else None,
        "business_area": {
            "business_area_id": business_area_entity.get("business_area_id"),
            "name": business_area_entity.get("name"),
            "slug": business_area_entity.get("slug"),
            "parent_business_area_id": business_area_entity.get("parent_business_area_id"),
            "parent": business_area_entity.get("parent"),
        } if business_area_entity else None,
        "model_year": model_year,
        "first_registration": _date_value(record.get("firstRegistration"), "first_registration"),
        "mileage_km": mileage_km,
        "price_krw": price_krw,
        "currency": _text_value(record.get("currency")),
        "source_status": source_status,
        "fuel_type": _text_value(record.get("fuelType")),
        "transmission": _text_value(record.get("transmission")),
        "color": _text_value(record.get("color")),
        "displacement_cc": _nonnegative_int(record.get("displacementCc"), "displacement_cc"),
        "accident_count": _nonnegative_int(record.get("accidentCount"), "accident_count"),
        "owner_change_count": _nonnegative_int(record.get("ownerChangeCount"), "owner_change_count"),
        "inspection_status": _text_value(record.get("inspectionStatus")),
        "source_created_at": source_created_at,
        "source_updated_at": source_updated_at,
        "dataset_epoch": dataset_epoch,
    }

    listing = {
        "listing_id": source_id,
        "listing_number": stable_content["listing_number"],
        "title": stable_content["title"],
        "description": stable_content["description"],
        "trim": stable_content["trim"],
        "model_id": model_id,
        "location_id": location_id,
        "dealer_code": dealer_code,
        "business_area_id": business_area_id,
        "model_year": model_year,
        "first_registration": stable_content["first_registration"],
        "mileage_km": mileage_km,
        "price_krw": price_krw,
        "currency": stable_content["currency"],
        "source_status": source_status,
        "fuel_type": stable_content["fuel_type"],
        "transmission": stable_content["transmission"],
        "color": stable_content["color"],
        "displacement_cc": stable_content["displacement_cc"],
        "accident_count": stable_content["accident_count"],
        "owner_change_count": stable_content["owner_change_count"],
        "inspection_status": stable_content["inspection_status"],
        "source_event_id": _text_value(record.get("_event_id")),
        "source_sequence": _nonnegative_int(record.get("_change_seq"), "source_sequence"),
        "content_hash": _canonical_hash(stable_content),
        "source_url": f"{base_url.rstrip('/')}/api/v1/cars/{source_id}",
        "source_created_at": source_created_at,
        "source_updated_at": source_updated_at,
        "run_id": run_id,
        "collected_at": normalized_collected_at,
        "created_at": now,
        "updated_at": now,
    }
    return {
        "listing": listing,
        "brand": brand_entity,
        "model": model_entity,
        "location": location_entity,
        "dealer": dealer_entity,
        "business_area": business_area_entity,
    }


def transform_records(
    records: Iterable[Mapping[str, Any]], *, settings: Settings, run_id: str, dataset_epoch: Optional[str]
) -> Tuple[List[Dict[str, Any]], List[RejectedRecord]]:
    collected_at = utc_now_iso()
    valid: List[Dict[str, Any]] = []
    rejected: List[RejectedRecord] = []
    for index, raw in enumerate(records):
        candidate = _change_record(raw)
        try:
            valid.append(
                transform_record(
                    candidate,
                    base_url=settings.base_url,
                    run_id=run_id,
                    collected_at=collected_at,
                    dataset_epoch=dataset_epoch,
                )
            )
        except PreprocessError as exc:
            rejected.append(RejectedRecord(index=index, error_code=exc.code, record_id=_record_id(candidate)))
    return valid, rejected
