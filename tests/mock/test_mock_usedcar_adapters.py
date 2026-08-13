from __future__ import annotations

import json
import re
import sys
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from collection.usedcar import CHANGES_ENDPOINT, INITIAL_ENDPOINT, UsedCarFetcher
from common.config import Settings
from common.contracts import LoadStats
from common.usedcar_hash import usedcar_content_hash
from loading.usedcar import SqlUpsertSink
from preprocessing.usedcar import transform_record


def _settings(tmp_path: Path) -> Settings:
    return Settings.from_env(
        {
            "USED_CAR_BASE_URL": "https://cars.example.test",
            "USED_CAR_API_KEY": "mock-key",
            "OUTPUT_DIR": str(tmp_path),
            "LOG_PATH": str(tmp_path / "events.jsonl"),
            "SQL_HOST": "sql.example.test",
            "SQL_PORT": "3307",
            "SQL_DATABASE": "mock_sales",
            "SQL_USER": "mock-user",
            "SQL_PASSWORD": "mock-password",
        },
        dotenv_path=tmp_path / "missing.env",
    )


class _PagingClient:
    def __init__(self, payloads: list[dict[str, Any]]) -> None:
        self.payloads = list(payloads)
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def get(self, path: str, **kwargs: Any) -> dict[str, Any]:
        self.calls.append((path, kwargs))
        return self.payloads.pop(0)


def _page(
    record_id: int,
    *,
    has_more: bool,
    next_url: str | None,
    sequence: int,
) -> dict[str, Any]:
    return {
        "data": [{"id": record_id}],
        "meta": {
            "has_more": has_more,
            "high_water_seq": sequence,
            "dataset_epoch": "epoch-1",
        },
        "links": {"next": next_url},
    }


def test_usedcar_fetcher_mock_initial_and_incremental_are_bounded_and_sequential() -> (
    None
):
    initial_client = _PagingClient(
        [
            _page(
                1,
                has_more=True,
                next_url=f"{INITIAL_ENDPOINT}?after_id=1&limit=2",
                sequence=1,
            ),
            _page(2, has_more=False, next_url=None, sequence=2),
        ]
    )
    clock = {"value": 0.0}
    sleeps: list[float] = []

    def monotonic() -> float:
        return clock["value"]

    def sleep(seconds: float) -> None:
        sleeps.append(seconds)
        clock["value"] += seconds

    initial = UsedCarFetcher(
        initial_client,
        interval_seconds=1.0,
        monotonic=monotonic,
        sleeper=sleep,
    )

    assert [page.records[0]["id"] for page in initial.iter_initial(2, 2)] == [1, 2]
    assert initial_client.calls == [
        (INITIAL_ENDPOINT, {"params": {"after_id": 0, "limit": 2}}),
        (f"{INITIAL_ENDPOINT}?after_id=1&limit=2", {}),
    ]
    assert sleeps == [1.0]

    incremental_client = _PagingClient(
        [_page(3, has_more=False, next_url=None, sequence=12)]
    )
    incremental = UsedCarFetcher(
        incremental_client,
        interval_seconds=1.0,
        monotonic=lambda: 0.0,
        sleeper=lambda _seconds: None,
    )

    assert [
        page.records[0]["id"]
        for page in incremental.iter_incremental(after_seq=11, limit=500, max_batches=1)
    ] == [3]
    assert incremental_client.calls == [
        (CHANGES_ENDPOINT, {"params": {"after_seq": 11, "limit": 500}})
    ]


_TABLE_KEYS = {
    "vehicle_brands": "brand_id",
    "vehicle_models": "model_id",
    "vehicle_locations": "location_id",
    "vehicle_dealers": "dealer_code",
    "vehicle_business_areas": "business_area_id",
    "vehicle_listings": "listing_id",
}


class _TransactionalCursor:
    def __init__(self, connection: "_TransactionalConnection") -> None:
        self.connection = connection
        self._rows: list[dict[str, Any]] = []
        self._row: tuple[Any, ...] | None = None

    def __enter__(self) -> "_TransactionalCursor":
        self.connection.working = deepcopy(self.connection.tables)
        self.connection.pending_runs = list(self.connection.pipeline_runs)
        return self

    def __exit__(self, *_args: Any) -> None:
        return None

    def execute(self, query: str, params: Any = None) -> None:
        compact = " ".join(query.split())
        self.connection.statements.append(("execute", compact, params))
        if compact.startswith("SELECT progress_key FROM pipeline_runs"):
            if self.connection.pipeline_runs:
                self._row = (self.connection.pipeline_runs[-1]["progress_key"],)
            else:
                self._row = None
            return
        if compact.startswith("SELECT ") and " FROM vehicle_" in compact:
            match = re.match(
                r"SELECT (.+) FROM (vehicle_[a-z_]+) WHERE ([a-z_]+) IN",
                compact,
            )
            assert match is not None
            columns = [value.strip() for value in match.group(1).split(",")]
            table = match.group(2)
            filter_column = match.group(3)
            selected = self.connection.working[table]
            keys = {str(value) for value in (params or ())}
            self._rows = [
                {column: row.get(column) for column in columns}
                for row in selected.values()
                if str(row.get(filter_column)) in keys
            ]
            return
        if compact.startswith("INSERT INTO pipeline_runs"):
            run = {
                "run_id": params[0],
                "pipeline_name": params[1],
                "collected_count": params[4],
                "preprocessed_count": params[5],
                "valid_count": params[6],
                "rejected_count": params[7],
                "inserted_count": params[8],
                "updated_count": params[9],
                "unchanged_count": params[10],
                "api_calls": params[11],
                "progress_key": params[12],
            }
            self.connection.pending_runs = [
                existing
                for existing in self.connection.pending_runs
                if existing["run_id"] != run["run_id"]
            ]
            self.connection.pending_runs.append(run)
            return
        raise AssertionError(f"unexpected SQL execute: {compact}")

    def executemany(self, query: str, values: Any) -> None:
        compact = " ".join(query.split())
        match = re.match(r"INSERT INTO (vehicle_[a-z_]+) \(([^)]+)\)", compact)
        assert match is not None
        table = match.group(1)
        columns = [value.strip() for value in match.group(2).split(",")]
        batch = list(values)
        self.connection.statements.append(("executemany", table, batch))
        if self.connection.fail_table == table:
            raise RuntimeError(f"mock {table} write failed")
        key_column = _TABLE_KEYS[table]
        for values_row in batch:
            row = dict(zip(columns, values_row))
            self.connection.working[table][str(row[key_column])] = row

    def fetchall(self) -> list[dict[str, Any]]:
        return list(self._rows)

    def fetchone(self) -> tuple[Any, ...] | None:
        return self._row


class _TransactionalConnection:
    def __init__(self, *, fail_table: str | None = None) -> None:
        self.tables = {name: {} for name in _TABLE_KEYS}
        self.working = deepcopy(self.tables)
        self.pipeline_runs: list[dict[str, Any]] = []
        self.pending_runs: list[dict[str, Any]] = []
        self.fail_table = fail_table
        self.statements: list[tuple[Any, ...]] = []
        self.commits = 0
        self.rollbacks = 0
        self.closed = False

    def cursor(self) -> _TransactionalCursor:
        return _TransactionalCursor(self)

    def commit(self) -> None:
        self.tables = deepcopy(self.working)
        self.pipeline_runs = list(self.pending_runs)
        self.commits += 1

    def rollback(self) -> None:
        self.working = deepcopy(self.tables)
        self.pending_runs = list(self.pipeline_runs)
        self.rollbacks += 1

    def close(self) -> None:
        self.closed = True


def _full_source_record() -> dict[str, Any]:
    return {
        "id": 101,
        "listingNumber": "LIST-101",
        "title": "Mock car",
        "description": "Stateful SQL adapter test",
        "trim": "Premium",
        "brand": {
            "id": 10,
            "name": "Brand A",
            "slug": "brand-a",
            "country": "KR",
        },
        "model": {
            "id": 20,
            "name": "Model X",
            "slug": "model-x",
            "bodyType": "SUV",
        },
        "location": {
            "id": 30,
            "province": "서울",
            "city": "서울",
            "sigungu": "강남구",
            "slug": "seoul-gangnam",
        },
        "dealer": {
            "code": "D-40",
            "displayName": "Dealer",
            "department": "Sales",
            "position": "Manager",
        },
        "businessArea": {
            "id": "AREA-CHILD",
            "name": "Child",
            "slug": "child",
            "parent": {
                "id": "AREA-PARENT",
                "name": "Parent",
                "slug": "parent",
            },
        },
        "modelYear": 2025,
        "firstRegistration": "2025-01-02",
        "mileageKm": 1000,
        "price": {"amount": 50000000},
        "currency": "KRW",
        "status": "AVAILABLE",
        "fuelType": "GASOLINE",
        "transmission": "AUTO",
        "color": "Black",
        "displacementCc": 1998,
        "accidentCount": 0,
        "ownerChangeCount": 0,
        "inspectionStatus": "PASS",
        "createdAt": "2026-08-01T00:00:00+00:00",
        "updatedAt": "2026-08-02T00:00:00+00:00",
    }


def _aggregate() -> dict[str, Any]:
    return transform_record(
        _full_source_record(),
        base_url="https://cars.example.test",
        run_id="source-run",
        collected_at="2026-08-13T00:00:00+00:00",
        dataset_epoch="epoch-1",
    )


def _stored_aggregate(
    connection: _TransactionalConnection, listing_id: str
) -> dict[str, Any]:
    listing = connection.tables["vehicle_listings"][listing_id]
    model = connection.tables["vehicle_models"].get(str(listing.get("model_id")))
    area = connection.tables["vehicle_business_areas"].get(
        str(listing.get("business_area_id"))
    )
    if area is not None and area.get("parent_business_area_id") not in (None, ""):
        area = dict(area)
        area["parent"] = connection.tables["vehicle_business_areas"].get(
            str(area["parent_business_area_id"])
        )
    return {
        "listing": listing,
        "brand": (
            connection.tables["vehicle_brands"].get(str(model.get("brand_id")))
            if model is not None
            else None
        ),
        "model": model,
        "location": connection.tables["vehicle_locations"].get(
            str(listing.get("location_id"))
        ),
        "dealer": connection.tables["vehicle_dealers"].get(
            str(listing.get("dealer_code"))
        ),
        "business_area": area,
    }


def _install_pymysql(
    monkeypatch: pytest.MonkeyPatch,
    connection: _TransactionalConnection,
) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []

    def connect(**kwargs: Any) -> _TransactionalConnection:
        calls.append(kwargs)
        return connection

    monkeypatch.setitem(sys.modules, "pymysql", SimpleNamespace(connect=connect))
    return calls


def test_usedcar_sql_sink_mock_writes_fk_order_checkpoint_and_idempotent_rerun(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _settings(tmp_path)
    connection = _TransactionalConnection()
    connect_calls = _install_pymysql(monkeypatch, connection)
    sink = SqlUpsertSink(settings)
    checkpoint = {
        "initialized": True,
        "after_seq": 12,
        "dataset_epoch": "epoch-1",
    }

    first = sink.save(
        [_aggregate()],
        checkpoint=checkpoint,
        run_id="batch-run-1",
        started_at="2026-08-13T00:00:00+00:00",
        run_counts={
            "collected_count": 2,
            "preprocessed_count": 2,
            "valid_count": 1,
            "rejected_count": 1,
            "api_calls": 1,
        },
    )
    first_write_order = [
        statement[1]
        for statement in connection.statements
        if statement[0] == "executemany"
    ]
    statement_count = len(connection.statements)
    second = sink.save(
        [_aggregate()],
        checkpoint=checkpoint,
        run_id="batch-run-2",
        started_at="2026-08-13T00:01:00+00:00",
    )
    second_statements = connection.statements[statement_count:]

    assert connect_calls == [
        {
            "host": "sql.example.test",
            "port": 3307,
            "user": "mock-user",
            "password": "mock-password",
            "database": "mock_sales",
            "charset": "utf8mb4",
            "autocommit": False,
        }
    ]
    assert first == LoadStats(inserted_count=1, updated_count=0, unchanged_count=0)
    assert second == LoadStats(inserted_count=0, updated_count=0, unchanged_count=1)
    assert first_write_order == [
        "vehicle_brands",
        "vehicle_models",
        "vehicle_locations",
        "vehicle_dealers",
        "vehicle_business_areas",
        "vehicle_listings",
    ]
    assert [
        row["business_area_id"]
        for row in connection.tables["vehicle_business_areas"].values()
    ] == ["AREA-PARENT", "AREA-CHILD"]
    assert not any(statement[0] == "executemany" for statement in second_statements)
    assert len(connection.pipeline_runs) == 2
    assert json.loads(connection.pipeline_runs[-1]["progress_key"]) == checkpoint
    assert connection.pipeline_runs[-1]["unchanged_count"] == 1
    assert connection.pipeline_runs[0]["collected_count"] == 2
    assert connection.pipeline_runs[0]["valid_count"] == 1
    assert connection.pipeline_runs[0]["rejected_count"] == 1
    assert connection.pipeline_runs[0]["api_calls"] == 1
    assert sink.load_checkpoint() == checkpoint
    assert connection.commits == 2
    assert connection.rollbacks == 0
    sink.close()
    assert connection.closed is True


def test_usedcar_sql_sink_mock_event_metadata_only_is_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    connection = _TransactionalConnection()
    _install_pymysql(monkeypatch, connection)
    sink = SqlUpsertSink(_settings(tmp_path))
    original = _aggregate()
    assert sink.save([original]).inserted_count == 1
    changed_event = deepcopy(original)
    changed_event["listing"]["source_event_id"] = "event-2"
    changed_event["listing"]["source_sequence"] = 2

    result = sink.save([changed_event])

    stored = connection.tables["vehicle_listings"]["101"]
    assert result == LoadStats(unchanged_count=1)
    assert stored["source_event_id"] == "event-2"
    assert stored["source_sequence"] == 2
    assert stored["content_hash"] == original["listing"]["content_hash"]


def test_usedcar_sql_sink_mock_shared_dimension_source_time_is_not_business_change(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    connection = _TransactionalConnection()
    _install_pymysql(monkeypatch, connection)
    sink = SqlUpsertSink(_settings(tmp_path))
    original = _aggregate()
    assert sink.save([original]).inserted_count == 1
    metadata_only = deepcopy(original)
    for name in ("brand", "model", "location", "dealer", "business_area"):
        metadata_only[name]["source_updated_at"] = "2026-08-03T00:00:00+00:00"

    result = sink.save([metadata_only])

    assert result == LoadStats(unchanged_count=1)
    assert (
        connection.tables["vehicle_listings"]["101"]["content_hash"]
        == original["listing"]["content_hash"]
    )


def test_usedcar_sql_sink_mock_sparse_event_merges_and_rehashes_final_row(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    connection = _TransactionalConnection()
    _install_pymysql(monkeypatch, connection)
    settings = _settings(tmp_path)
    sink = SqlUpsertSink(settings)
    original = _aggregate()
    assert sink.save([original]).inserted_count == 1
    sparse = transform_record(
        {
            "id": 101,
            "title": "Changed by sparse event",
            "_event_id": "event-3",
            "_change_seq": 3,
        },
        base_url=settings.base_url,
        run_id="sparse-run",
        collected_at="2026-08-13T01:00:00+00:00",
        dataset_epoch="epoch-1",
    )

    result = sink.save([sparse])

    stored = connection.tables["vehicle_listings"]["101"]
    assert result == LoadStats(updated_count=1)
    assert stored["title"] == "Changed by sparse event"
    assert stored["description"] == original["listing"]["description"]
    assert stored["model_id"] == original["listing"]["model_id"]
    stored_aggregate = _stored_aggregate(connection, "101")
    assert stored["content_hash"] == usedcar_content_hash(stored_aggregate)


def test_usedcar_sql_sink_mock_dimension_only_change_updates_aggregate_hash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    connection = _TransactionalConnection()
    _install_pymysql(monkeypatch, connection)
    sink = SqlUpsertSink(_settings(tmp_path))
    original = _aggregate()
    assert sink.save([original]).inserted_count == 1
    changed = deepcopy(original)
    changed["model"]["name"] = "Model Y"

    result = sink.save([changed])

    stored_listing = connection.tables["vehicle_listings"]["101"]
    stored_model = connection.tables["vehicle_models"]["20"]
    aggregate = _stored_aggregate(connection, "101")
    assert result == LoadStats(updated_count=1)
    assert stored_model["name"] == "Model Y"
    assert stored_listing["content_hash"] == usedcar_content_hash(aggregate)
    assert stored_listing["content_hash"] != original["listing"]["content_hash"]


def test_usedcar_sql_sink_mock_shared_dimension_change_rehashes_all_references(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    connection = _TransactionalConnection()
    _install_pymysql(monkeypatch, connection)
    sink = SqlUpsertSink(_settings(tmp_path))
    first = _aggregate()
    second = deepcopy(first)
    second["listing"]["listing_id"] = "102"
    second["listing"]["listing_number"] = "LIST-102"
    second["listing"]["title"] = "Second mock car"
    second["listing"]["content_hash"] = usedcar_content_hash(second)
    assert sink.save([first, second]) == LoadStats(inserted_count=2)
    second_hash_before = connection.tables["vehicle_listings"]["102"]["content_hash"]
    changed = deepcopy(first)
    changed["model"]["name"] = "Shared Model Y"

    result = sink.save([changed])

    stored_first = connection.tables["vehicle_listings"]["101"]
    stored_second = connection.tables["vehicle_listings"]["102"]
    first_aggregate = _stored_aggregate(connection, "101")
    second_aggregate = _stored_aggregate(connection, "102")
    assert result == LoadStats(updated_count=1)
    assert stored_first["content_hash"] == usedcar_content_hash(first_aggregate)
    assert stored_second["content_hash"] == usedcar_content_hash(second_aggregate)
    assert stored_second["content_hash"] != second_hash_before


def test_usedcar_sql_sink_mock_rolls_back_all_tables_and_checkpoint_on_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    connection = _TransactionalConnection(fail_table="vehicle_locations")
    _install_pymysql(monkeypatch, connection)
    sink = SqlUpsertSink(_settings(tmp_path))

    with pytest.raises(RuntimeError, match="vehicle_locations write failed"):
        sink.save(
            [_aggregate()],
            checkpoint={"initialized": True, "after_seq": 12},
            run_id="batch-run-failure",
            started_at="2026-08-13T00:00:00+00:00",
        )

    assert connection.commits == 0
    assert connection.rollbacks == 1
    assert all(not rows for rows in connection.tables.values())
    assert connection.pipeline_runs == []
