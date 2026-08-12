from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from common import logging_utils as logging_module
from loading import faq as faq_module
from loading import registration as registration_module
from loading import usedcar as usedcar_module
from loading.faq import JsonlFaqUpsertSink
from loading.registration import (
    JsonQuotaLedger,
    JsonlRegistrationUpsertSink,
    RegistrationStateStore,
    SqlRegistrationUpsertSink,
)
from loading.usedcar import JsonlUpsertSink, SqlUpsertSink


FIRST_LOAD = "2026-02-01T00:00:00+00:00"
SECOND_LOAD = "2026-02-02T00:00:00+00:00"
THIRD_LOAD = "2026-02-03T00:00:00+00:00"
SOURCE_TIME = "1999-01-01T00:00:00+00:00"


def _read_one(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8").splitlines()[0])


def test_common_logger_uses_canonical_utc_formatter(monkeypatch: Any, tmp_path: Path) -> None:
    monkeypatch.setattr(logging_module, "utc_now_iso", lambda: FIRST_LOAD)

    logging_module.JsonlLogger(tmp_path / "events.jsonl").event("INFO", "test", "ok")

    assert _read_one(tmp_path / "events.jsonl")["ts"] == FIRST_LOAD


def test_faq_jsonl_owns_load_timestamps_and_preserves_idempotent_rows(
    monkeypatch: Any, tmp_path: Path
) -> None:
    path = tmp_path / "faq.jsonl"
    sink = JsonlFaqUpsertSink(path)
    document = {
        "faq_id": "faq-1",
        "content_hash": "hash-1",
        "created_at": SOURCE_TIME,
        "updated_at": SOURCE_TIME,
        "collected_at": SOURCE_TIME,
    }

    monkeypatch.setattr(faq_module, "utc_now_iso", lambda: FIRST_LOAD)
    assert sink.save([document]).inserted_count == 1
    first = _read_one(path)
    assert first["created_at"] == FIRST_LOAD
    assert first["updated_at"] == FIRST_LOAD

    changed = {**document, "content_hash": "hash-2", "created_at": SOURCE_TIME}
    monkeypatch.setattr(faq_module, "utc_now_iso", lambda: SECOND_LOAD)
    assert sink.save([changed]).updated_count == 1
    second = _read_one(path)
    assert second["created_at"] == FIRST_LOAD
    assert second["updated_at"] == SECOND_LOAD

    monkeypatch.setattr(faq_module, "utc_now_iso", lambda: THIRD_LOAD)
    assert sink.save([changed]).unchanged_count == 1
    assert _read_one(path)["updated_at"] == SECOND_LOAD


def test_usedcar_jsonl_updates_nested_listing_and_dimension_load_timestamps(
    monkeypatch: Any, tmp_path: Path
) -> None:
    path = tmp_path / "vehicle_listings.jsonl"
    sink = JsonlUpsertSink(path)
    row = {
        "listing": {
            "listing_id": "listing-1",
            "content_hash": "hash-1",
            "created_at": SOURCE_TIME,
            "updated_at": SOURCE_TIME,
        },
        "brand": {
            "brand_id": "brand-1",
            "created_at": SOURCE_TIME,
            "updated_at": SOURCE_TIME,
        },
    }

    monkeypatch.setattr(usedcar_module, "utc_now_iso", lambda: FIRST_LOAD)
    assert sink.save([row]).inserted_count == 1
    first = _read_one(path)
    assert first["listing"]["created_at"] == FIRST_LOAD
    assert first["brand"]["updated_at"] == FIRST_LOAD

    changed = {
        **row,
        "listing": {**row["listing"], "content_hash": "hash-2"},
        "brand": {**row["brand"]},
    }
    monkeypatch.setattr(usedcar_module, "utc_now_iso", lambda: SECOND_LOAD)
    assert sink.save([changed]).updated_count == 1
    second = _read_one(path)
    assert second["listing"]["created_at"] == FIRST_LOAD
    assert second["listing"]["updated_at"] == SECOND_LOAD
    assert second["brand"]["created_at"] == FIRST_LOAD


def test_registration_jsonl_owns_load_timestamps(monkeypatch: Any, tmp_path: Path) -> None:
    path = tmp_path / "registration.jsonl"
    sink = JsonlRegistrationUpsertSink(path)
    row = {
        "report_month": "2026-02-01",
        "sido_name": "서울",
        "sigungu_name": "강남구",
        "vehicle_type": "승용",
        "usage_type": "자가용",
        "quantity": 1,
        "content_hash": "hash-1",
        "created_at": SOURCE_TIME,
        "updated_at": SOURCE_TIME,
    }

    monkeypatch.setattr(registration_module, "utc_now_iso", lambda: FIRST_LOAD)
    assert sink.save([row]).inserted_count == 1
    first = _read_one(path)
    assert first["created_at"] == FIRST_LOAD
    assert first["updated_at"] == FIRST_LOAD

    changed = {**row, "content_hash": "hash-2"}
    monkeypatch.setattr(registration_module, "utc_now_iso", lambda: SECOND_LOAD)
    assert sink.save([changed]).updated_count == 1
    second = _read_one(path)
    assert second["created_at"] == FIRST_LOAD
    assert second["updated_at"] == SECOND_LOAD


def test_registration_quota_json_uses_canonical_utc_call_time(
    monkeypatch: Any, tmp_path: Path
) -> None:
    monkeypatch.setattr(registration_module, "utc_now_iso", lambda: FIRST_LOAD)
    store = RegistrationStateStore(tmp_path / "state.json")
    ledger = JsonQuotaLedger(store, limit=1, time_zone="UTC")

    ledger.reserve()

    assert store.load()["last_call_at"] == FIRST_LOAD


def test_sql_sinks_normalize_datetime_values_before_mysql_conversion() -> None:
    source_value = "2026-02-01T09:00:00.987654+09:00"

    assert SqlUpsertSink._sql_value(source_value, "source_updated_at") == "2026-02-01 00:00:00"
    assert SqlRegistrationUpsertSink._sql_value(
        {"updated_at": source_value}, "updated_at"
    ) == "2026-02-01 00:00:00"
