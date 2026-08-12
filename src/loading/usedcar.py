"""Used-car checkpoint, JSONL, and normalized MySQL persistence adapters."""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Sequence

from common.config import Settings
from common.contracts import LoadStats
from common.sql_utils import to_sql_date, to_sql_datetime
from common.time_utils import format_utc_datetime, utc_now_iso

from .common import atomic_write


_LOAD_OWNED_COLUMNS = frozenset({"run_id", "collected_at", "created_at", "updated_at"})
_NUMERIC_COLUMNS = frozenset(
    {
        "brand_id",
        "model_id",
        "location_id",
        "model_year",
        "mileage_km",
        "price_krw",
        "displacement_cc",
        "accident_count",
        "owner_change_count",
        "source_sequence",
    }
)


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


def _with_load_timestamps(
    record: Mapping[str, Any],
    previous: Mapping[str, Any] | None,
    load_now: str,
) -> Dict[str, Any]:
    """Apply loading-owned timestamps to the listing aggregate and dimensions."""

    value = dict(record)
    for name in ("listing", "brand", "model", "location", "dealer", "business_area"):
        current = value.get(name)
        if not isinstance(current, Mapping):
            continue
        previous_entity = previous.get(name) if previous is not None else None
        previous_created_at = (
            previous_entity.get("created_at")
            if isinstance(previous_entity, Mapping)
            else None
        )
        normalized = dict(current)
        if previous_created_at not in (None, ""):
            normalized["created_at"] = format_utc_datetime(previous_created_at, required=True)
        else:
            normalized["created_at"] = load_now
        normalized["updated_at"] = load_now
        value[name] = normalized
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
        load_now = utc_now_iso()
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
                continue
            else:
                updated += 1
            existing[key] = _with_load_timestamps(row, previous, load_now)
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
            return to_sql_datetime(format_utc_datetime(value))
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
        updates: List[str] = []
        for column in columns:
            if column in {key_column, "created_at"}:
                continue
            if column in {"run_id", "collected_at", "updated_at"}:
                updates.append(f"{column}=VALUES({column})")
            elif column == "content_hash":
                updates.append(f"{column}=COALESCE(VALUES({column}), {column})")
            else:
                # Incremental events may omit unchanged values.  Preserve the
                # existing non-null value in that case.
                updates.append(f"{column}=COALESCE(VALUES({column}), {column})")
        return (
            f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders}) "
            f"ON DUPLICATE KEY UPDATE {', '.join(updates)}"
        )

    @classmethod
    def _comparison_value(cls, value: Any, column: str) -> Any:
        """Normalize a source or DB value before comparing it for idempotency."""

        normalized = cls._sql_value(value, column)
        if isinstance(normalized, date):
            return normalized.isoformat()
        if column in _NUMERIC_COLUMNS and normalized not in (None, ""):
            try:
                return Decimal(str(normalized))
            except (InvalidOperation, ValueError):
                pass
        return normalized

    @classmethod
    def _read_existing(
        cls,
        cursor: Any,
        table: str,
        columns: Sequence[str],
        key_column: str,
        keys: Sequence[Any],
    ) -> Dict[str, Dict[str, Any]]:
        if not keys:
            return {}
        selected = tuple(
            column
            for column in columns
            if column not in _LOAD_OWNED_COLUMNS
        )
        placeholders = ", ".join(["%s"] * len(keys))
        cursor.execute(
            f"SELECT {', '.join(selected)} FROM {table} "
            f"WHERE {key_column} IN ({placeholders})",
            tuple(keys),
        )
        result: Dict[str, Dict[str, Any]] = {}
        for raw_row in cursor.fetchall():
            if isinstance(raw_row, Mapping):
                row = dict(raw_row)
            else:
                row = dict(zip(selected, raw_row))
            if row.get(key_column) not in (None, ""):
                result[str(row[key_column])] = row
        return result

    @classmethod
    def _row_changed(
        cls,
        row: Mapping[str, Any],
        previous: Mapping[str, Any],
        columns: Sequence[str],
        key_column: str,
    ) -> bool:
        """Apply the SQL omitted-value contract to a single existing row."""

        for column in columns:
            if column in _LOAD_OWNED_COLUMNS or column == key_column:
                continue
            incoming = cls._comparison_value(row.get(column), column)
            if incoming is None:
                # SQL upserts preserve an existing non-null value when an
                # incremental event omits that field.
                continue
            existing = cls._comparison_value(previous.get(column), column)
            if incoming != existing:
                return True
        return False

    @classmethod
    def _partition_rows(
        cls,
        rows: Sequence[Mapping[str, Any]],
        previous: Mapping[str, Mapping[str, Any]],
        columns: Sequence[str],
        key_column: str,
    ) -> tuple[List[Mapping[str, Any]], int, int, int]:
        writes: List[Mapping[str, Any]] = []
        inserted = updated = unchanged = 0
        for row in rows:
            key = row.get(key_column)
            previous_row = previous.get(str(key))
            if previous_row is None:
                inserted += 1
                writes.append(row)
            elif cls._row_changed(row, previous_row, columns, key_column):
                updated += 1
                writes.append(row)
            else:
                unchanged += 1
        return writes, inserted, updated, unchanged

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

    def load_checkpoint(self, pipeline_name: str = "used_car") -> Dict[str, Any]:
        """Read the latest successful SQL progress key for a pipeline."""

        with self.connection.cursor() as cursor:
            cursor.execute(
                "SELECT progress_key FROM pipeline_runs "
                "WHERE pipeline_name=%s AND status='SUCCESS' "
                "AND progress_key IS NOT NULL "
                "ORDER BY ended_at DESC, updated_at DESC LIMIT 1",
                (pipeline_name,),
            )
            row = cursor.fetchone()
        if not row:
            return {}
        raw = row.get("progress_key") if isinstance(row, Mapping) else row[0]
        if raw in (None, ""):
            return {}
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        try:
            value = json.loads(str(raw))
        except (TypeError, json.JSONDecodeError) as exc:
            raise RuntimeError("SQL checkpoint progress_key is invalid") from exc
        if not isinstance(value, dict):
            raise RuntimeError("SQL checkpoint progress_key must be an object")
        return value

    @staticmethod
    def _progress_key(value: Mapping[str, Any]) -> str:
        progress_key = json.dumps(dict(value), ensure_ascii=False, separators=(",", ":"))
        if len(progress_key) > 256:
            raise ValueError("checkpoint progress_key exceeds 256 characters")
        return progress_key

    def _record_pipeline_success(
        self,
        cursor: Any,
        *,
        run_id: str,
        started_at: str,
        checkpoint: Mapping[str, Any],
        stats: LoadStats,
    ) -> None:
        """Record successful batch progress in the same SQL transaction."""

        ended_at = utc_now_iso()
        started_sql = to_sql_datetime(started_at)
        ended_sql = to_sql_datetime(ended_at)
        progress_key = self._progress_key(checkpoint)
        cursor.execute(
            "INSERT INTO pipeline_runs "
            "(run_id, pipeline_name, status, started_at, ended_at, "
            "inserted_count, updated_count, unchanged_count, progress_key, "
            "created_at, updated_at) "
            "VALUES (%s, %s, 'SUCCESS', %s, %s, %s, %s, %s, %s, %s, %s) "
            "ON DUPLICATE KEY UPDATE status='SUCCESS', ended_at=VALUES(ended_at), "
            "inserted_count=VALUES(inserted_count), updated_count=VALUES(updated_count), "
            "unchanged_count=VALUES(unchanged_count), progress_key=VALUES(progress_key), "
            "error_code=NULL, error_message=NULL, updated_at=VALUES(updated_at)",
            (
                run_id,
                "used_car",
                started_sql,
                ended_sql,
                stats.inserted_count,
                stats.updated_count,
                stats.unchanged_count,
                progress_key,
                ended_sql,
                ended_sql,
            ),
        )

    def save(
        self,
        rows: Sequence[Mapping[str, Any]],
        *,
        checkpoint: Mapping[str, Any] | None = None,
        run_id: str | None = None,
        started_at: str | None = None,
    ) -> LoadStats:
        unique_rows: Dict[str, Mapping[str, Any]] = {}
        for row in rows:
            unique_rows[_record_key(row)] = row
        records = list(unique_rows.values())
        if not records and checkpoint is None:
            return LoadStats()
        if checkpoint is not None and not run_id:
            raise ValueError("run_id is required when recording a SQL checkpoint")

        load_now = utc_now_iso()
        brands = self._unique_entities(records, "brand", "brand_id")
        models = self._unique_entities(records, "model", "model_id")
        locations = self._unique_entities(records, "location", "location_id")
        dealers = self._unique_entities(records, "dealer", "dealer_code")
        areas = self._business_area_entities(records)
        listing_keys = tuple(_record_key(record) for record in records)

        stats = LoadStats()

        try:
            with self.connection.cursor() as cursor:
                existing_brands = self._read_existing(
                    cursor,
                    "vehicle_brands",
                    self.BRAND_COLUMNS,
                    "brand_id",
                    [row.get("brand_id") for row in brands],
                )
                existing_models = self._read_existing(
                    cursor,
                    "vehicle_models",
                    self.MODEL_COLUMNS,
                    "model_id",
                    [row.get("model_id") for row in models],
                )
                existing_locations = self._read_existing(
                    cursor,
                    "vehicle_locations",
                    self.LOCATION_COLUMNS,
                    "location_id",
                    [row.get("location_id") for row in locations],
                )
                existing_dealers = self._read_existing(
                    cursor,
                    "vehicle_dealers",
                    self.DEALER_COLUMNS,
                    "dealer_code",
                    [row.get("dealer_code") for row in dealers],
                )
                existing_areas = self._read_existing(
                    cursor,
                    "vehicle_business_areas",
                    self.BUSINESS_AREA_COLUMNS,
                    "business_area_id",
                    [row.get("business_area_id") for row in areas],
                )
                existing_listings = self._read_existing(
                    cursor,
                    "vehicle_listings",
                    self.LISTING_COLUMNS,
                    "listing_id",
                    listing_keys,
                )

                brand_writes, _, _, _ = self._partition_rows(
                    brands, existing_brands, self.BRAND_COLUMNS, "brand_id"
                )
                model_writes, _, _, _ = self._partition_rows(
                    models, existing_models, self.MODEL_COLUMNS, "model_id"
                )
                location_writes, _, _, _ = self._partition_rows(
                    locations, existing_locations, self.LOCATION_COLUMNS, "location_id"
                )
                dealer_writes, _, _, _ = self._partition_rows(
                    dealers, existing_dealers, self.DEALER_COLUMNS, "dealer_code"
                )
                area_writes, _, _, _ = self._partition_rows(
                    areas, existing_areas, self.BUSINESS_AREA_COLUMNS, "business_area_id"
                )
                listing_writes, inserted, updated, unchanged = self._partition_rows(
                    [_listing(record) for record in records],
                    existing_listings,
                    self.LISTING_COLUMNS,
                    "listing_id",
                )
                stats = LoadStats(inserted, updated, unchanged)

                normalized_records = [
                    _with_load_timestamps(record, None, load_now) for record in records
                ]
                normalized_by_key = {
                    _record_key(record): record for record in normalized_records
                }
                normalized_brands = self._unique_entities(normalized_records, "brand", "brand_id")
                normalized_models = self._unique_entities(normalized_records, "model", "model_id")
                normalized_locations = self._unique_entities(normalized_records, "location", "location_id")
                normalized_dealers = self._unique_entities(normalized_records, "dealer", "dealer_code")
                normalized_areas = self._business_area_entities(normalized_records)

                brand_write_keys = {str(row["brand_id"]) for row in brand_writes}
                model_write_keys = {str(row["model_id"]) for row in model_writes}
                location_write_keys = {str(row["location_id"]) for row in location_writes}
                dealer_write_keys = {str(row["dealer_code"]) for row in dealer_writes}
                area_write_keys = {str(row["business_area_id"]) for row in area_writes}

                # FK-safe order: brand -> model -> location -> dealer ->
                # business-area parent/child -> listing.  Only new/changed
                # rows are written; unchanged rows remain untouched.
                self._upsert_table(
                    cursor,
                    "vehicle_brands",
                    self.BRAND_COLUMNS,
                    "brand_id",
                    [
                        row for row in normalized_brands
                        if str(row["brand_id"]) in brand_write_keys
                    ],
                )
                self._upsert_table(
                    cursor,
                    "vehicle_models",
                    self.MODEL_COLUMNS,
                    "model_id",
                    [
                        row for row in normalized_models
                        if str(row["model_id"]) in model_write_keys
                    ],
                )
                self._upsert_table(
                    cursor,
                    "vehicle_locations",
                    self.LOCATION_COLUMNS,
                    "location_id",
                    [
                        row for row in normalized_locations
                        if str(row["location_id"]) in location_write_keys
                    ],
                )
                self._upsert_table(
                    cursor,
                    "vehicle_dealers",
                    self.DEALER_COLUMNS,
                    "dealer_code",
                    [
                        row for row in normalized_dealers
                        if str(row["dealer_code"]) in dealer_write_keys
                    ],
                )
                self._upsert_table(
                    cursor,
                    "vehicle_business_areas",
                    self.BUSINESS_AREA_COLUMNS,
                    "business_area_id",
                    [
                        row for row in normalized_areas
                        if str(row["business_area_id"]) in area_write_keys
                    ],
                )
                self._upsert_table(
                    cursor,
                    "vehicle_listings",
                    self.LISTING_COLUMNS,
                    "listing_id",
                    [
                        _listing(normalized_by_key[str(row["listing_id"])])
                        for row in listing_writes
                    ],
                )
                if checkpoint is not None:
                    assert run_id is not None
                    self._record_pipeline_success(
                        cursor,
                        run_id=run_id,
                        started_at=started_at or load_now,
                        checkpoint=checkpoint,
                        stats=stats,
                    )
            self.connection.commit()
        except Exception:
            self.connection.rollback()
            raise
        return stats

    def close(self) -> None:
        self.connection.close()


def sink_for(settings: Settings, sink_name: str) -> Any:
    if sink_name == "json":
        return JsonlUpsertSink(settings.output_dir / "vehicle_listings.jsonl")
    if sink_name == "sql":
        return SqlUpsertSink(settings)
    raise ValueError(f"unsupported used-car sink: {sink_name}")


__all__ = ["CheckpointStore", "JsonlUpsertSink", "LoadStats", "SqlUpsertSink", "sink_for"]
