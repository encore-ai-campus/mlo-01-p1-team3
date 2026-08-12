"""원본 차량 JSON을 MySQL cars 행으로 정규화한다."""

# =============================================================================
# [차량 전처리 시작] 중첩 객체 값·날짜 정규화
# 기능: 원본 normalize_car()가 사용하는 보조 함수를 제공한다.
# 원본 위치: load_cars_initial.py의 value_from(), normalize_date()
# =============================================================================
def value_from(obj, *keys, default=None):
    if not isinstance(obj, dict):
        return default

    for key in keys:
        value = obj.get(key)
        if value is not None:
            return value

    return default


def normalize_date(value):
    if not value:
        return None

    if isinstance(value, str):
        return value[:10]

    return value
# =============================================================================
# [차량 전처리 끝]
# =============================================================================


# =============================================================================
# [차량 전처리 시작] 차량 JSON 정규화
# 기능: 원본 차량 객체 또는 증분 change payload를 cars 테이블 입력 구조로 변환한다.
# 원본 위치: load_cars_initial.py의 normalize_car()
# =============================================================================
def normalize_car(raw):
    brand = raw.get("brand") or {}
    model = raw.get("model") or {}
    dealer = raw.get("dealer") or {}
    area = raw.get("businessArea") or {}
    location = raw.get("location") or {}

    return {
        "car_id": raw.get("id"),
        "listing_number": raw.get("listingNumber"),
        "dealer_id": dealer.get("code"),
        "business_area_code": area.get("id"),
        "brand": value_from(brand, "name", default=(brand if isinstance(brand, str) else None)),
        "model": value_from(model, "name", default=(model if isinstance(model, str) else None)),
        "trim": raw.get("trim"),
        "model_year": raw.get("modelYear"),
        "first_registration_date": normalize_date(raw.get("firstRegistration") or raw.get("firstRegistrationDate") or raw.get("firstRegisteredAt")),
        "mileage_km": raw.get("mileageKm"),
        "price": raw.get("price"),
        "currency": raw.get("currency"),
        "fuel_type": raw.get("fuelType") or raw.get("fuel"),
        "transmission": raw.get("transmission"),
        "color": raw.get("color"),
        "displacement_cc": raw.get("displacementCc") or raw.get("engineDisplacementCc"),
        "status": raw.get("status"),
        "accident_count": raw.get("accidentCount"),
        "owner_change_count": raw.get("ownerChangeCount"),
        "inspection_status": raw.get("inspectionStatus"),
        "province": value_from(location, "province", "sido", "region"),
        "city": value_from(location, "city", "sigungu", "district"),
        "listing_date": normalize_date(raw.get("listingDate") or raw.get("registeredDate")),
    }
# =============================================================================
# [차량 전처리 끝]
# =============================================================================
