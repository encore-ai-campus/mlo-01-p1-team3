from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from migrations.mongo.ensure_indexes import FAQ_VALIDATOR
from migrations.sql.run import split_sql
from common import logging_utils as logging_module
from loading import faq as faq_module
from loading import registration as registration_module
from loading import usedcar as usedcar_module
from loading.faq import JsonlFaqUpsertSink, MongoFaqUpsertSink
from loading.registration import (
    JsonQuotaLedger,
    JsonlRegistrationUpsertSink,
    RegistrationStateStore,
    SqlRegistrationUpsertSink,
)
from loading.usedcar import JsonlUpsertSink, SqlUpsertSink
from pipelines.usedcar import _require_incremental_contract


FIRST_LOAD = "2026-02-01T00:00:00+00:00"
SECOND_LOAD = "2026-02-02T00:00:00+00:00"
THIRD_LOAD = "2026-02-03T00:00:00+00:00"
SOURCE_TIME = "1999-01-01T00:00:00+00:00"


def _read_one(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8").splitlines()[0])


def _faq_document(content_hash: str = "a" * 64) -> dict[str, Any]:
    return {
        "faq_id": "faq-1",
        "question": "질문",
        "answer": "답변",
        "brand": "브랜드",
        "category": "카테고리",
        "source_url": "https://source.example/faq/faq-1",
        "source_updated_at": "2026-01-01T00:00:00+00:00",
        "license": "test-license",
        "attribution": "test-attribution",
        "content_hash": content_hash,
        "is_active": True,
        "run_id": "run-1",
        "collected_at": SOURCE_TIME,
        "created_at": SOURCE_TIME,
        "updated_at": SOURCE_TIME,
    }


class _FakeCursor:
    def __init__(
        self,
        *,
        listing_hash: str | None = None,
        registration_hash: str | None = None,
        progress_key: str | None = None,
        fail_on_executemany: bool = False,
    ) -> None:
        self.listing_hash = listing_hash
        self.registration_hash = registration_hash
        self.progress_key = progress_key
        self.fail_on_executemany = fail_on_executemany
        self.executed: list[tuple[str, Any]] = []
        self.executemany_calls: list[tuple[str, Any]] = []
        self._rows: list[Any] = []
        self._one: Any = None

    def __enter__(self) -> "_FakeCursor":
        return self

    def __exit__(self, *args: Any) -> None:
        return None

    def execute(self, query: str, params: Any = None) -> None:
        self.executed.append((query, params))
        if "FROM vehicle_listings" in query:
            self._rows = (
                [{"listing_id": "listing-1", "content_hash": self.listing_hash}]
                if self.listing_hash is not None
                else []
            )
        elif "FROM vehicle_registration_reports" in query:
            self._rows = (
                [
                    (
                        "2026-02-01",
                        "서울",
                        "강남구",
                        "승용",
                        "자가용",
                        self.registration_hash,
                    )
                ]
                if self.registration_hash is not None
                else []
            )
        elif "FROM pipeline_runs" in query:
            self._one = (self.progress_key,) if self.progress_key is not None else None

    def executemany(self, query: str, values: Any) -> None:
        if self.fail_on_executemany:
            raise RuntimeError("fake SQL write failed")
        self.executemany_calls.append((query, values))

    def fetchall(self) -> list[Any]:
        return self._rows

    def fetchone(self) -> Any:
        return self._one


class _FakeConnection:
    def __init__(self, cursor: _FakeCursor) -> None:
        self._cursor = cursor
        self.commit_count = 0
        self.rollback_count = 0

    def cursor(self) -> _FakeCursor:
        return self._cursor

    def commit(self) -> None:
        self.commit_count += 1

    def rollback(self) -> None:
        self.rollback_count += 1

    def close(self) -> None:
        return None


class _FakeMongoCollection:
    def __init__(self) -> None:
        self.updates: list[tuple[Any, Any, bool]] = []

    def find_one(self, *_args: Any, **_kwargs: Any) -> None:
        return None

    def update_one(self, query: Any, update: Any, *, upsert: bool) -> None:
        self.updates.append((query, update, upsert))


def _usedcar_row(content_hash: str) -> dict[str, Any]:
    return {
        "listing": {
            "listing_id": "listing-1",
            "content_hash": content_hash,
        }
    }


def _registration_row(content_hash: str) -> dict[str, Any]:
    return {
        "report_month": "2026-02-01",
        "sido_name": "서울",
        "sigungu_name": "강남구",
        "vehicle_type": "승용",
        "usage_type": "자가용",
        "quantity": 1,
        "source_name": "molit_car_registration",
        "source_url": "https://stat.molit.go.kr/registration",
        "run_id": "run-1",
        "collected_at": SOURCE_TIME,
        "content_hash": content_hash,
    }


def test_common_logger_uses_canonical_utc_formatter(monkeypatch: Any, tmp_path: Path) -> None:
    monkeypatch.setattr(logging_module, "utc_now_iso", lambda: FIRST_LOAD)

    logging_module.JsonlLogger(tmp_path / "events.jsonl").event("INFO", "test", "ok")

    assert _read_one(tmp_path / "events.jsonl")["ts"] == FIRST_LOAD


def test_faq_jsonl_owns_load_timestamps_and_preserves_idempotent_rows(
    monkeypatch: Any, tmp_path: Path
) -> None:
    path = tmp_path / "faq.jsonl"
    sink = JsonlFaqUpsertSink(path)
    document = _faq_document()

    monkeypatch.setattr(faq_module, "utc_now_iso", lambda: FIRST_LOAD)
    assert sink.save([document]).inserted_count == 1
    first = _read_one(path)
    assert first["created_at"] == FIRST_LOAD
    assert first["updated_at"] == FIRST_LOAD

    changed = {**document, "content_hash": "b" * 64, "created_at": SOURCE_TIME}
    monkeypatch.setattr(faq_module, "utc_now_iso", lambda: SECOND_LOAD)
    assert sink.save([changed]).updated_count == 1
    second = _read_one(path)
    assert second["created_at"] == FIRST_LOAD
    assert second["updated_at"] == SECOND_LOAD

    monkeypatch.setattr(faq_module, "utc_now_iso", lambda: THIRD_LOAD)
    assert sink.save([changed]).unchanged_count == 1
    assert _read_one(path)["updated_at"] == SECOND_LOAD


def test_faq_mongo_sink_converts_all_timestamps_to_bson_date_inputs(
    monkeypatch: Any,
) -> None:
    collection = _FakeMongoCollection()
    sink = MongoFaqUpsertSink.__new__(MongoFaqUpsertSink)
    sink._collection = collection
    monkeypatch.setattr(faq_module, "utc_now_iso", lambda: FIRST_LOAD)

    stats = sink.save([_faq_document()])

    assert stats.inserted_count == 1
    _, update, upsert = collection.updates[0]
    assert upsert is True
    assert all(
        isinstance(update["$set"][name], datetime)
        and update["$set"][name].tzinfo == timezone.utc
        for name in ("source_updated_at", "collected_at", "updated_at")
    )
    assert isinstance(update["$setOnInsert"]["created_at"], datetime)
    assert update["$setOnInsert"]["created_at"].tzinfo == timezone.utc


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
        "source_name": "molit_car_registration",
        "source_url": "https://stat.molit.go.kr/registration",
        "run_id": "run-1",
        "collected_at": SOURCE_TIME,
        "content_hash": "a" * 64,
        "created_at": SOURCE_TIME,
        "updated_at": SOURCE_TIME,
    }

    monkeypatch.setattr(registration_module, "utc_now_iso", lambda: FIRST_LOAD)
    assert sink.save([row]).inserted_count == 1
    first = _read_one(path)
    assert first["created_at"] == FIRST_LOAD
    assert first["updated_at"] == FIRST_LOAD

    changed = {**row, "content_hash": "b" * 64}
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


def test_sql_usedcar_unchanged_rows_are_not_written() -> None:
    cursor = _FakeCursor(listing_hash="a" * 64)
    connection = _FakeConnection(cursor)
    sink = SqlUpsertSink.__new__(SqlUpsertSink)
    sink.connection = connection

    stats = sink.save([_usedcar_row("a" * 64)])

    assert stats.inserted_count == 0
    assert stats.updated_count == 0
    assert stats.unchanged_count == 1
    assert cursor.executemany_calls == []
    assert connection.commit_count == 1


def test_sql_registration_unchanged_rows_are_not_written() -> None:
    cursor = _FakeCursor(registration_hash="a" * 64)
    connection = _FakeConnection(cursor)
    sink = SqlRegistrationUpsertSink.__new__(SqlRegistrationUpsertSink)
    sink.connection = connection

    stats = sink.save([_registration_row("a" * 64)])

    assert stats.inserted_count == 0
    assert stats.updated_count == 0
    assert stats.unchanged_count == 1
    assert cursor.executemany_calls == []
    assert connection.commit_count == 1


def test_sql_changed_rows_are_written_and_pipeline_progress_is_transactional() -> None:
    cursor = _FakeCursor(listing_hash="a" * 64)
    connection = _FakeConnection(cursor)
    sink = SqlUpsertSink.__new__(SqlUpsertSink)
    sink.connection = connection

    stats = sink.save(
        [_usedcar_row("b" * 64)],
        checkpoint={"initialized": True, "after_seq": 11},
        run_id="run-1",
        started_at=FIRST_LOAD,
    )

    assert stats.updated_count == 1
    assert len(cursor.executemany_calls) == 1
    assert any("INSERT INTO pipeline_runs" in query for query, _ in cursor.executed)
    assert connection.commit_count == 1
    assert connection.rollback_count == 0


def test_sql_write_failure_rolls_back_without_commit() -> None:
    cursor = _FakeCursor(fail_on_executemany=True)
    connection = _FakeConnection(cursor)
    sink = SqlUpsertSink.__new__(SqlUpsertSink)
    sink.connection = connection

    with pytest.raises(RuntimeError, match="fake SQL write failed"):
        sink.save([_usedcar_row("a" * 64)])

    assert connection.commit_count == 0
    assert connection.rollback_count == 1


def test_sql_checkpoint_load_reads_latest_progress_object() -> None:
    progress = json.dumps({"initialized": True, "after_seq": 19})
    cursor = _FakeCursor(progress_key=progress)
    connection = _FakeConnection(cursor)
    sink = SqlUpsertSink.__new__(SqlUpsertSink)
    sink.connection = connection

    assert sink.load_checkpoint() == {"initialized": True, "after_seq": 19}


def test_faq_and_registration_sinks_reject_incomplete_prepared_contracts(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="question"):
        JsonlFaqUpsertSink(tmp_path / "faq.jsonl").save(
            [{"faq_id": "faq-1", "content_hash": "a" * 64}]
        )

    invalid_registration = _registration_row("a" * 64)
    invalid_registration["quantity"] = -1
    with pytest.raises(registration_module.RegistrationError, match="quantity"):
        JsonlRegistrationUpsertSink(tmp_path / "registration.jsonl").save(
            [invalid_registration]
        )


def test_mongo_validator_and_incremental_contract_are_explicit() -> None:
    required = set(FAQ_VALIDATOR["$jsonSchema"]["required"])
    assert {"faq_id", "content_hash", "run_id", "updated_at"}.issubset(required)
    properties = FAQ_VALIDATOR["$jsonSchema"]["properties"]
    assert all(
        properties[name]["bsonType"] == "date"
        for name in ("source_updated_at", "collected_at", "created_at", "updated_at")
    )

    with pytest.raises(Exception) as exc_info:
        _require_incremental_contract({"high_water_seq": None})
    assert getattr(exc_info.value, "code") == "incremental_contract_missing"

    assert _require_incremental_contract({"high_water_seq": 5}) == 5


def test_sql_migration_splitter_preserves_quoted_semicolons() -> None:
    statements = split_sql(
        "CREATE TABLE `sample` (value VARCHAR(16)); "
        "INSERT INTO sample VALUES ('a;b');"
    )

    assert statements == [
        "CREATE TABLE `sample` (value VARCHAR(16))",
        "INSERT INTO sample VALUES ('a;b')",
    ]
