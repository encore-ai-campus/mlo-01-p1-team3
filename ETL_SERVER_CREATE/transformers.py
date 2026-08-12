"""원본 JSON을 데이터베이스 적재용 구조로 변환한다."""

from typing import Any


# ============================================================================
# TRANSFORMERS START: cars API payload를 MySQL 컬럼 구조로 정규화한다.
# ============================================================================


def value_from(value: Any, *keys: str, default: Any = None) -> Any:
    """딕셔너리에서 후보 키 순서대로 첫 번째 존재 값을 반환한다."""
    if not isinstance(value, dict):
        return default
    for key in keys:
        if value.get(key) is not None:
            return value[key]
    return default


def normalize_date(value: Any) -> Any:
    """ISO 날짜시간 문자열을 MySQL DATE 형식으로 잘라낸다."""
    return value[:10] if isinstance(value, str) and value else value


def normalize_car(raw: dict[str, Any]) -> dict[str, Any]:
    """기존 차량 API 스키마를 cars 테이블의 평면 컬럼으로 변환한다."""
    brand = raw.get("brand") or {}
    model = raw.get("model") or {}
    dealer = raw.get("dealer") or {}
    area = raw.get("businessArea") or {}
    location = raw.get("location") or {}
    return {
        "car_id": raw.get("id"), "listing_number": raw.get("listingNumber"),
        "dealer_id": dealer.get("code"), "business_area_code": area.get("id"),
        "brand": value_from(brand, "name", default=brand if isinstance(brand, str) else None),
        "model": value_from(model, "name", default=model if isinstance(model, str) else None),
        "trim": raw.get("trim"), "model_year": raw.get("modelYear"),
        "first_registration_date": normalize_date(raw.get("firstRegistration") or raw.get("firstRegistrationDate") or raw.get("firstRegisteredAt")),
        "mileage_km": raw.get("mileageKm"), "price": raw.get("price"), "currency": raw.get("currency"),
        "fuel_type": raw.get("fuelType") or raw.get("fuel"), "transmission": raw.get("transmission"),
        "color": raw.get("color"), "displacement_cc": raw.get("displacementCc") or raw.get("engineDisplacementCc"),
        "status": raw.get("status"), "accident_count": raw.get("accidentCount"),
        "owner_change_count": raw.get("ownerChangeCount"), "inspection_status": raw.get("inspectionStatus"),
        "province": value_from(location, "province", "sido", "region"),
        "city": value_from(location, "city", "sigungu", "district"),
        "listing_date": normalize_date(raw.get("listingDate") or raw.get("registeredDate")),
    }


# ============================================================================
# TRANSFORMERS END: 데이터 정규화 기능의 끝.
# ============================================================================
