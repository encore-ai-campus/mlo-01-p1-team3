"""Used-car checkpoint, JSONL, and normalized MySQL persistence adapters."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Sequence

from common.config import Settings
from common.sql_utils import to_sql_date, to_sql_datetime

from .common import atomic_write


@dataclass(frozen=True)
class LoadStats:
    inserted_count: int = 0
    updated_count: int = 0
    unchanged_count: int = 0


def _listing(record: Mapping[str, Any]) -> Mapping[str, Any]:
    listing = record.get("listing")
    if not isinstance(listing, Mapping):
        raise ValueError("prepared used-car record must contain a listing object")
    if listing.get("listing_id") in (None, ""):
        raise ValueError("prepared used-car listing_id is required")
    return listing


def _record_key(record: Mapping[str, Any]) -> str:
    return str(_listing(record)["listing_id"])


def _entity(record: Mapping[str, Any], name: str) -> Mapping[str, Any] | None:
    value = record.get(name)
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise ValueError(f"prepared used-car {name} must be an object or null")
    return value


class CheckpointStore:
    """Atomic local checkpoint advanced by the pipeline after successful load."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> Dict[str, Any]:
        if not self.path.exists():
            return {"initialized": False, "after_seq": 0, "dataset_epoch": None}
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError("checkpoint is unreadable") from exc
        if not isinstance(value, dict):
            raise RuntimeError("checkpoint root must be an object")
        return value

    def save(self, value: Mapping[str, Any]) -> None:
        atomic_write(self.path, json.dumps(dict(value), ensure_ascii=False, indent=2) + "\n")


class JsonlUpsertSink:
    """Deterministic local sink keyed by ``listing.listing_id``."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def _read(self) -> Dict[str, Dict[str, Any]]:
        rows: Dict[str, Dict[str, Any]] = {}
        if not self.path.exists():
            return rows
        try:
            lines = self.path.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            raise RuntimeError("used-car JSONL output could not be read") from exc
        for index, line in enumerate(lines, start=1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise RuntimeError(f"used-car JSONL output is invalid at line {index}") from exc
            if not isinstance(row, dict):
                raise RuntimeError(f"used-car JSONL record is invalid at line {index}")
            rows[_record_key(row)] = row
        return rows

    def save(self, rows: Sequence[Mapping[str, Any]]) -> LoadStats:
        existing = self._read()
        inserted = updated = unchanged = 0
        # Duplicate keys in one prepared batch are resolved deterministically
        # by the final item, at listing grain.
        incoming: Dict[str, Mapping[str, Any]] = {}
        for row in rows:
            incoming[_record_key(row)] = row
        for key, row in incoming.items():
            listing = _listing(row)
            previous = existing.get(key)
            if previous is None:
                inserted += 1
            elif _listing(previous).get("content_hash") == listing.get("content_hash"):
                unchanged += 1
            else:
                updated += 1
            existing[key] = dict(row)
        ordered = sorted(existing.values(), key=_record_key)
        atomic_write(
            self.path,
            "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in ordered),
        )
        return LoadStats(inserted, updated, unchanged)


class SqlUpsertSink:
    """Write dimensions and listings in one MySQL transaction."""

    BRAND_COLUMNS = (
        "brand_id", "name", "slug", "country", "source_updated_at", "run_id",
        "collected_at", "created_at", "updated_at",
    )
    MODEL_COLUMNS = (
        "model_id", "brand_id", "name", "slug", "body_type", "source_updated_at",
        "run_id", "collected_at", "created_at", "updated_at",
    )
    LOCATION_COLUMNS = (
        "location_id", "province", "city", "sigungu", "slug", "source_updated_at",
        "run_id", "collected_at", "created_at", "updated_at",
    )
    DEALER_COLUMNS = (
        "dealer_code", "display_name", "department", "position", "source_updated_at",
        "run_id", "collected_at", "created_at", "updated_at",
    )
    BUSINESS_AREA_COLUMNS = (
        "business_area_id", "name", "slug", "parent_business_area_id",
        "source_updated_at", "run_id", "collected_at", "created_at", "updated_at",
    )
    LISTING_COLUMNS = (
        "listing_id", "listing_number", "title", "description", "trim", "model_id",
        "location_id", "dealer_code", "business_area_id", "model_year",
        "first_registration", "mileage_km", "price_krw", "currency", "source_status",
        "fuel_type", "transmission", "color", "displacement_cc", "accident_count",
        "owner_change_count", "inspection_status", "source_event_id", "source_sequence",
        "content_hash", "source_url", "source_created_at", "source_updated_at", "run_id",
        "collected_at", "created_at", "updated_at",
    )

    def __init__(self, settings: Settings) -> None:
        if not settings.sql_host or not settings.sql_user:
            raise RuntimeError("SQL_HOST/SQL_JDBC_URL and SQL_USER are required for --sink sql")
        try:
            import pymysql  # type: ignore
        except ImportError as exc:
            raise RuntimeError("pymysql is required for --sink sql") from exc
        self.connection = pymysql.connect(
            host=settings.sql_host,
            port=settings.sql_port,
            user=settings.sql_user,
            password=settings.sql_password,
            database=settings.sql_database,
            charset="utf8mb4",
            autocommit=False,
        )

    @staticmethod
    def _sql_value(value: Any, column: str) -> Any:
        if column == "first_registration":
            return to_sql_date(value)
        if column in {
            "source_created_at", "source_updated_at", "collected_at", "created_at", "updated_at"
        }:
            return to_sql_datetime(value)
        return value

    @classmethod
    def _values(
        cls,
        rows: Iterable[Mapping[str, Any]],
        columns: Sequence[str],
    ) -> List[tuple[Any, ...]]:
        return [tuple(cls._sql_value(row.get(column), column) for column in columns) for row in rows]

    @classmethod
    def _upsert_query(cls, table: str, columns: Sequence[str], key_column: str) -> str:
        placeholders = ", ".join(["%s"] * len(columns))
        always_update = {"run_id", "collected_at", "updated_at", "content_hash"}
        updates: List[str] = []
        for column in columns:
            if column in {key_column, "created_at"}:
                continue
            if column in always_update:
                updates.append(f"{column}=VALUES({column})")
            else:
                # Incremental events may omit unchanged values.  Preserve the
                # existing non-null value in that case.
                updates.append(f"{column}=COALESCE(VALUES({column}), {column})")
        return (
            f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders}) "
            f"ON DUPLICATE KEY UPDATE {', '.join(updates)}"
        )

    @staticmethod
    def _unique_entities(
        rows: Sequence[Mapping[str, Any]],
        name: str,
        key: str,
    ) -> List[Mapping[str, Any]]:
        entities: Dict[str, Mapping[str, Any]] = {}
        for record in rows:
            value = _entity(record, name)
            if value is not None and value.get(key) not in (None, ""):
                entities[str(value[key])] = value
        return list(entities.values())

    @staticmethod
    def _business_area_entities(rows: Sequence[Mapping[str, Any]]) -> List[Mapping[str, Any]]:
        """Build parent stubs and order parents before children for self-FK."""

        entities: Dict[str, Mapping[str, Any]] = {}
        for record in rows:
            value = _entity(record, "business_area")
            if value is None or value.get("business_area_id") in (None, ""):
                continue
            parent = value.get("parent")
            parent_id = parent.get("business_area_id") if isinstance(parent, Mapping) else None
            if parent_id not in (None, ""):
                entities.setdefault(
                    str(parent_id),
                    {
                        "business_area_id": parent_id,
                        "name": parent.get("name"),
                        "slug": parent.get("slug"),
                        "parent_business_area_id": None,
                        "source_updated_at": value.get("source_updated_at"),
                        "run_id": value.get("run_id"),
                        "collected_at": value.get("collected_at"),
                        "created_at": value.get("created_at"),
                        "updated_at": value.get("updated_at"),
                    },
                )
            entities[str(value["business_area_id"])] = value
        return sorted(entities.values(), key=lambda item: bool(item.get("parent_business_area_id")))

    def _upsert_table(
        self,
        cursor: Any,
        table: str,
        columns: Sequence[str],
        key_column: str,
        rows: Sequence[Mapping[str, Any]],
    ) -> None:
        if rows:
            cursor.executemany(
                self._upsert_query(table, columns, key_column),
                self._values(rows, columns),
            )

    def save(self, rows: Sequence[Mapping[str, Any]]) -> LoadStats:
        unique_rows: Dict[str, Mapping[str, Any]] = {}
        for row in rows:
            unique_rows[_record_key(row)] = row
        records = list(unique_rows.values())
        if not records:
            return LoadStats()

        brands = self._unique_entities(records, "brand", "brand_id")
        models = self._unique_entities(records, "model", "model_id")
        locations = self._unique_entities(records, "location", "location_id")
        dealers = self._unique_entities(records, "dealer", "dealer_code")
        areas = self._business_area_entities(records)
        listing_keys = tuple(_record_key(record) for record in records)
        placeholders = ", ".join(["%s"] * len(listing_keys))

        try:
            with self.connection.cursor() as cursor:
                # FK-safe order: brand -> model -> location -> dealer ->
                # business-area parent/child -> listing.
                self._upsert_table(cursor, "vehicle_brands", self.BRAND_COLUMNS, "brand_id", brands)
                self._upsert_table(cursor, "vehicle_models", self.MODEL_COLUMNS, "model_id", models)
                self._upsert_table(cursor, "vehicle_locations", self.LOCATION_COLUMNS, "location_id", locations)
                self._upsert_table(cursor, "vehicle_dealers", self.DEALER_COLUMNS, "dealer_code", dealers)
                self._upsert_table(
                    cursor,
                    "vehicle_business_areas",
                    self.BUSINESS_AREA_COLUMNS,
                    "business_area_id",
                    areas,
                )
                cursor.execute(
                    "SELECT listing_id, content_hash FROM vehicle_listings "
                    f"WHERE listing_id IN ({placeholders})",
                    listing_keys,
                )
                previous = {
                    str(key): None if content_hash is None else str(content_hash)
                    for key, content_hash in cursor.fetchall()
                }
                cursor.executemany(
                    self._upsert_query("vehicle_listings", self.LISTING_COLUMNS, "listing_id"),
                    self._values((_listing(record) for record in records), self.LISTING_COLUMNS),
                )
            self.connection.commit()
        except Exception:
            self.connection.rollback()
            raise

        inserted = updated = unchanged = 0
        for record in records:
            key = _record_key(record)
            content_hash = _listing(record).get("content_hash")
            if key not in previous:
                inserted += 1
            elif previous[key] == content_hash:
                unchanged += 1
            else:
                updated += 1
        return LoadStats(inserted, updated, unchanged)

    def close(self) -> None:
        self.connection.close()


def sink_for(settings: Settings, sink_name: str) -> Any:
    if sink_name == "json":
        return JsonlUpsertSink(settings.output_dir / "vehicle_listings.jsonl")
    if sink_name == "sql":
        return SqlUpsertSink(settings)
    raise ValueError(f"unsupported used-car sink: {sink_name}")


__all__ = ["CheckpointStore", "JsonlUpsertSink", "LoadStats", "SqlUpsertSink", "sink_for"]
