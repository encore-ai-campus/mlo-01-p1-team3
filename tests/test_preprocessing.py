from __future__ import annotations

import ast
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from common.config import Settings
from preprocessing.faq import transform_faq_records, transform_faq_record
from preprocessing.registration import (
    transform_registration_records,
    transform_registration_row,
)
from preprocessing.usedcar import transform_record, transform_records


def settings() -> Settings:
    return Settings.from_env(
        {
            "USED_CAR_BASE_URL": "https://cars.example.test",
            "FAQ_LICENSE": "test-license",
            "FAQ_ATTRIBUTION": "test-attribution",
            "REGISTRATION_API_URL": "https://registration.example.test/api",
        }
    )


def faq_record(**overrides: Any) -> dict[str, Any]:
    record: dict[str, Any] = {
        "faq_id": "faq-1",
        "question": "  What &amp; where?  ",
        "answer": "  Visit the source.\n",
        "brand": "Brand A",
        "category": "Purchase",
        "source_url": "https://source.example.test/faqs/1#answer",
        "reviewed_at": "2026-08-01",
        "license": "source-license",
        "attribution": "source-attribution",
    }
    record.update(overrides)
    return record


def used_car_record(**overrides: Any) -> dict[str, Any]:
    record: dict[str, Any] = {
        "id": 101,
        "listingNumber": "L-101",
        "title": " Sedan ",
        "description": " One owner ",
        "trim": "Premium",
        "brand": {"id": 1, "name": "Brand A", "slug": "brand-a", "country": "KR"},
        "model": {
            "id": 2,
            "name": "Model A",
            "slug": "model-a",
            "bodyType": "sedan",
        },
        "location": {
            "id": 3,
            "province": "Seoul",
            "city": "Seoul",
            "sigungu": "Gangnam",
            "slug": "seoul-gangnam",
        },
        "dealer": {
            "code": "D-1",
            "displayName": "Dealer A",
            "department": "Sales",
            "position": "Manager",
        },
        "businessArea": {
            "id": "BA-1",
            "name": "Passenger",
            "slug": "passenger",
            "parent": {"id": "BA-0", "name": "Vehicle", "slug": "vehicle"},
        },
        "modelYear": "2020",
        "firstRegistration": "2020-02-29",
        "mileageKm": "12,345",
        "price": {"amount": "20,000"},
        "currency": "KRW",
        "status": "available",
        "fuelType": "gasoline",
        "transmission": "automatic",
        "color": "white",
        "displacementCc": 1_998,
        "accidentCount": 0,
        "ownerChangeCount": 1,
        "inspectionStatus": "passed",
        "createdAt": "2026-01-01T00:00:00Z",
        "updatedAt": "2026-01-02T03:00:00+09:00",
    }
    record.update(overrides)
    return record


def registration_row(**overrides: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "월": "2026-01",
        "시도명": "서울",
        "시군구": "강남구",
        "승용>관용": "1,234",
        "승용>자가용": "-",
        "총계>계": 0,
    }
    row.update(overrides)
    return row


def test_faq_normalizes_text_url_date_and_emits_canonical_document() -> None:
    result = transform_faq_record(
        faq_record(),
        settings=settings(),
        run_id="run-1",
        collected_at="2026-08-02T00:00:00+00:00",
    )

    assert result["faq_id"] == "faq-1"
    assert result["question"] == "What & where?"
    assert result["answer"] == "Visit the source."
    assert result["source_url"] == "https://source.example.test/faqs/1"
    assert result["source_updated_at"] == "2026-08-01T00:00:00+00:00"
    assert result["license"] == "source-license"
    assert result["attribution"] == "source-attribution"
    assert result["run_id"] == "run-1"
    assert result["collected_at"] == "2026-08-02T00:00:00+00:00"
    assert "reviewed_at" not in result
    assert len(result["content_hash"]) == 64


def test_faq_normalizes_collected_at_to_common_datetime_format() -> None:
    result = transform_faq_record(
        faq_record(),
        settings=settings(),
        run_id="run-1",
        collected_at="2026-08-02T09:00:00.987654+09:00",
    )

    assert result["collected_at"] == "2026-08-02T00:00:00+00:00"
    assert result["created_at"] == "2026-08-02T00:00:00+00:00"
    assert result["updated_at"] == "2026-08-02T00:00:00+00:00"


def test_faq_accepts_compact_date_and_uses_fallback_id() -> None:
    result = transform_faq_record(
        faq_record(faq_id=None, reviewed_at="20260801"),
        settings=settings(),
        run_id="run-1",
        collected_at="2026-08-02T00:00:00+00:00",
    )

    assert result["faq_id"]
    assert result["source_updated_at"] == "2026-08-01T00:00:00+00:00"


def test_faq_content_hash_excludes_run_metadata_but_changes_with_content() -> None:
    first = transform_faq_record(
        faq_record(),
        settings=settings(),
        run_id="run-1",
        collected_at="2026-08-02T00:00:00+00:00",
    )
    same_content = transform_faq_record(
        faq_record(),
        settings=settings(),
        run_id="run-2",
        collected_at="2026-08-03T00:00:00+00:00",
    )
    changed_content = transform_faq_record(
        faq_record(answer="A changed answer."),
        settings=settings(),
        run_id="run-2",
        collected_at="2026-08-03T00:00:00+00:00",
    )

    assert first["content_hash"] == same_content["content_hash"]
    assert first["content_hash"] != changed_content["content_hash"]


@pytest.mark.parametrize(
    ("field", "value", "error_code"),
    [
        ("question", "", "missing_question"),
        ("answer", "", "missing_answer"),
        ("brand", "", "missing_brand"),
        ("category", "", "missing_category"),
        ("source_url", "not-a-url", "invalid_source_url"),
        ("reviewed_at", None, "missing_reviewed_at"),
        ("reviewed_at", "2026-08-01T00:00:00Z", "invalid_reviewed_at"),
        ("reviewed_at", "2026-02-31", "invalid_reviewed_at"),
    ],
)
def test_faq_rejects_missing_or_invalid_contract_values(
    field: str, value: Any, error_code: str
) -> None:
    record = faq_record(**{field: value})

    valid, rejected = transform_faq_records(
        [record],
        settings=settings(),
        run_id="run-1",
        collected_at="2026-08-02T00:00:00+00:00",
    )

    assert valid == []
    assert len(rejected) == 1
    assert rejected[0].index == 0
    assert rejected[0].error_code == error_code


def test_faq_uses_configured_license_and_attribution_when_record_omits_them() -> None:
    record = faq_record(license="", attribution="")

    valid, rejected = transform_faq_records(
        [record],
        settings=settings(),
        run_id="run-1",
        collected_at="2026-08-02T00:00:00+00:00",
    )

    assert rejected == []
    assert valid[0]["license"] == "test-license"
    assert valid[0]["attribution"] == "test-attribution"


def test_faq_rejects_when_license_and_attribution_policy_are_both_missing() -> None:
    record = faq_record(license="", attribution="")
    no_policy = replace(settings(), faq_license="", faq_attribution="")

    valid, rejected = transform_faq_records(
        [record],
        settings=no_policy,
        run_id="run-1",
        collected_at="2026-08-02T00:00:00+00:00",
    )

    assert valid == []
    assert [(item.error_code, item.faq_id) for item in rejected] == [
        ("missing_license", "faq-1")
    ]


def test_faq_batch_separates_valid_and_rejected_records() -> None:
    valid, rejected = transform_faq_records(
        [faq_record(), faq_record(faq_id="faq-2", answer="")],
        settings=settings(),
        run_id="run-1",
        collected_at="2026-08-02T00:00:00+00:00",
    )

    assert [item["faq_id"] for item in valid] == ["faq-1"]
    assert [(item.index, item.error_code, item.faq_id) for item in rejected] == [
        (1, "missing_answer", "faq-2")
    ]


def test_used_car_transforms_change_envelope_and_normalizes_aggregate() -> None:
    valid, rejected = transform_records(
        [{"eventId": "event-1", "seq": 7, "record": used_car_record()}],
        settings=settings(),
        run_id="run-1",
        dataset_epoch="epoch-1",
    )

    assert rejected == []
    assert len(valid) == 1
    aggregate = valid[0]
    listing = aggregate["listing"]

    assert listing["listing_id"] == "101"
    assert listing["listing_number"] == "L-101"
    assert listing["model_year"] == 2020
    assert listing["mileage_km"] == 12_345
    assert listing["price_krw"] == 20_000
    assert listing["source_status"] == "AVAILABLE"
    assert listing["source_event_id"] == "event-1"
    assert listing["source_sequence"] == 7
    assert listing["first_registration"] == "2020-02-29"
    assert listing["source_created_at"] == "2026-01-01T00:00:00+00:00"
    assert listing["source_updated_at"] == "2026-01-01T18:00:00+00:00"
    assert listing["source_url"] == "https://cars.example.test/api/v1/cars/101"
    assert aggregate["model"]["brand_id"] == 1
    assert aggregate["business_area"]["parent"]["business_area_id"] == "BA-0"
    assert len(listing["content_hash"]) == 64


def test_used_car_normalizes_collected_at_and_generated_metadata_precision() -> None:
    result = transform_record(
        used_car_record(),
        base_url=settings().base_url,
        run_id="run-1",
        collected_at="2026-02-01T09:00:00.987654+09:00",
        dataset_epoch="epoch-1",
    )

    listing = result["listing"]
    assert listing["collected_at"] == "2026-02-01T00:00:00+00:00"
    assert "." not in listing["created_at"]
    assert "." not in listing["updated_at"]


@pytest.mark.parametrize(
    ("record", "error_code"),
    [
        (used_car_record(id=None, listingNumber=None), "missing_listing_id"),
        (used_car_record(status="archived"), "invalid_status"),
        (used_car_record(mileageKm=-1), "invalid_mileage_km"),
        (used_car_record(brand={"name": "missing-id"}), "missing_brand_id"),
        (used_car_record(firstRegistration="2026-02-31"), "invalid_first_registration"),
    ],
)
def test_used_car_rejects_contract_violations(record: dict[str, Any], error_code: str) -> None:
    valid, rejected = transform_records(
        [record],
        settings=settings(),
        run_id="run-1",
        dataset_epoch="epoch-1",
    )

    assert valid == []
    assert len(rejected) == 1
    assert rejected[0].error_code == error_code


def test_used_car_supports_listing_number_when_source_id_is_absent() -> None:
    valid, rejected = transform_records(
        [used_car_record(id=None)],
        settings=settings(),
        run_id="run-1",
        dataset_epoch=None,
    )

    assert rejected == []
    assert valid[0]["listing"]["listing_id"] == "L-101"


def test_registration_flattens_composite_measures_and_normalizes_quantities() -> None:
    rows = transform_registration_row(
        registration_row(referenceDate="20260115"),
        period="2026-01",
        settings=settings(),
        run_id="run-1",
        collected_at="2026-02-01T00:00:00+00:00",
    )

    assert [(row["vehicle_type"], row["usage_type"], row["quantity"]) for row in rows] == [
        ("승용", "관용", 1234),
        ("승용", "자가용", None),
        ("총계", "계", 0),
    ]
    assert all(row["report_month"] == "2026-01-01" for row in rows)
    assert all(row["source_name"] == "molit_car_registration" for row in rows)
    assert all(row["source_url"] == settings().registration_api_url for row in rows)
    assert len({row["content_hash"] for row in rows}) == len(rows)


def test_registration_normalizes_collected_at_to_common_datetime_format() -> None:
    rows = transform_registration_row(
        registration_row(),
        period="2026-01",
        settings=settings(),
        run_id="run-1",
        collected_at="2026-02-01T09:00:00.987654+09:00",
    )

    assert rows[0]["collected_at"] == "2026-02-01T00:00:00+00:00"
    assert rows[0]["created_at"] == "2026-02-01T00:00:00+00:00"
    assert rows[0]["updated_at"] == "2026-02-01T00:00:00+00:00"


def test_registration_preserves_business_key_for_twenty_source_measures() -> None:
    row = {
        "월": "2026.01",
        "시도명": "서울",
        "시군구": "강남구",
        **{f"차량{i}>용도{i}": str(i) for i in range(20)},
    }

    valid, rejected = transform_registration_records(
        [row],
        period="202601",
        settings=settings(),
        run_id="run-1",
        collected_at="2026-02-01T00:00:00+00:00",
    )

    assert rejected == []
    assert len(valid) == 20
    assert valid[0]["report_month"] == "2026-01-01"
    assert valid[0]["sido_name"] == "서울"
    assert valid[0]["sigungu_name"] == "강남구"
    assert valid[0]["vehicle_type"] == "차량0"
    assert valid[0]["usage_type"] == "용도0"
    assert valid[0]["quantity"] == 0


def test_registration_supports_direct_dimension_fixture_shape() -> None:
    row = {
        "reference_month": "2026-02",
        "province": "부산",
        "district": "해운대구",
        "vehicle_type": "승용",
        "usage_type": "자가용",
        "quantity": "10,000",
    }

    rows = transform_registration_row(
        row,
        period="2026-02",
        settings=settings(),
        run_id="run-1",
        collected_at="2026-03-01T00:00:00+00:00",
    )

    assert rows[0]["report_month"] == "2026-02-01"
    assert rows[0]["quantity"] == 10_000
    assert rows[0]["vehicle_type"] == "승용"
    assert rows[0]["usage_type"] == "자가용"


def test_registration_batch_rejects_missing_location_without_losing_index() -> None:
    valid, rejected = transform_registration_records(
        [registration_row(), registration_row(시도명="")],
        period="2026-01",
        settings=settings(),
        run_id="run-1",
        collected_at="2026-02-01T00:00:00+00:00",
    )

    assert len(valid) == 3
    assert [(item.index, item.error_code) for item in rejected] == [
        (1, "missing_sido_name")
    ]


@pytest.mark.parametrize(
    ("row", "period", "error_code"),
    [
        (registration_row(), "2026-13", "invalid_reference_month"),
        (registration_row(**{"승용>관용": "-1"}), "2026-01", "invalid_quantity"),
        (
            {"월": "2026-01", "시도명": "서울", "시군구": "강남구"},
            "2026-01",
            "missing_registration_measure",
        ),
    ],
)
def test_registration_rejects_invalid_period_quantity_or_measure(
    row: dict[str, Any], period: str, error_code: str
) -> None:
    valid, rejected = transform_registration_records(
        [row],
        period=period,
        settings=settings(),
        run_id="run-1",
        collected_at="2026-02-01T00:00:00+00:00",
    )

    assert valid == []
    assert [(item.index, item.error_code) for item in rejected] == [(0, error_code)]


def test_preprocessing_modules_do_not_import_other_pipeline_stages() -> None:
    source_root = Path(__file__).resolve().parents[1] / "src" / "preprocessing"
    forbidden = {"collection", "loading", "pipelines", "requests", "pymongo", "pymysql", "sqlalchemy"}

    for path in source_root.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        imported_roots: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_roots.update(alias.name.split(".", 1)[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported_roots.add(node.module.split(".", 1)[0])
        assert not imported_roots.intersection(forbidden), (path, imported_roots)
