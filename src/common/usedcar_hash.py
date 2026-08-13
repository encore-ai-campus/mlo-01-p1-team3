"""Canonical business-content hashing for normalized used-car aggregates."""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Mapping

from .time_utils import format_utc_date, format_utc_datetime


LISTING_CONTENT_COLUMNS = (
    "listing_id",
    "listing_number",
    "title",
    "description",
    "trim",
    "model_id",
    "location_id",
    "dealer_code",
    "business_area_id",
    "model_year",
    "first_registration",
    "mileage_km",
    "price_krw",
    "currency",
    "source_status",
    "fuel_type",
    "transmission",
    "color",
    "displacement_cc",
    "accident_count",
    "owner_change_count",
    "inspection_status",
    "source_created_at",
    "source_updated_at",
)

ENTITY_CONTENT_COLUMNS = {
    "brand": ("brand_id", "name", "slug", "country"),
    "model": ("model_id", "brand_id", "name", "slug", "body_type"),
    "location": ("location_id", "province", "city", "sigungu", "slug"),
    "dealer": ("dealer_code", "display_name", "department", "position"),
    "business_area": (
        "business_area_id",
        "name",
        "slug",
        "parent_business_area_id",
    ),
}
_LISTING_DATE_COLUMNS = frozenset({"first_registration"})
_LISTING_DATETIME_COLUMNS = frozenset({"source_created_at", "source_updated_at"})


def _canonical_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return format_utc_datetime(value, required=True)
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else str(value)
    return value


def _selected(mapping: Mapping[str, Any] | None, columns: tuple[str, ...]) -> Any:
    if mapping is None:
        return None
    return {column: _canonical_value(mapping.get(column)) for column in columns}


def _listing_value(value: Any, column: str) -> Any:
    if value in (None, ""):
        return None
    if column in _LISTING_DATE_COLUMNS:
        return format_utc_date(value, required=True)
    if column in _LISTING_DATETIME_COLUMNS:
        return format_utc_datetime(value, required=True)
    return _canonical_value(value)


def usedcar_content_hash(record: Mapping[str, Any]) -> str:
    """Hash final persisted business content, excluding event/load metadata."""

    listing = record.get("listing")
    if not isinstance(listing, Mapping):
        raise ValueError("used-car aggregate must contain a listing object")
    stable: dict[str, Any] = {
        "listing": {
            column: _listing_value(listing.get(column), column)
            for column in LISTING_CONTENT_COLUMNS
        }
    }
    stable.update(
        {
            name: _selected(
                record.get(name) if isinstance(record.get(name), Mapping) else None,
                columns,
            )
            for name, columns in ENTITY_CONTENT_COLUMNS.items()
        }
    )
    area = record.get("business_area")
    parent = area.get("parent") if isinstance(area, Mapping) else None
    if isinstance(parent, Mapping):
        stable["business_area_parent"] = _selected(
            parent,
            ("business_area_id", "name", "slug"),
        )
    encoded = json.dumps(
        stable,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


__all__ = [
    "ENTITY_CONTENT_COLUMNS",
    "LISTING_CONTENT_COLUMNS",
    "usedcar_content_hash",
]
