"""Registration state, quota, JSONL, and MySQL persistence adapters."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Mapping, Sequence
from zoneinfo import ZoneInfo

from common.config import Settings
from common.contracts import LoadStats as CommonLoadStats
from common.sql_utils import to_sql_date, to_sql_datetime
from common.time_utils import format_utc_date, format_utc_datetime, utc_now_iso

from .common import atomic_write


class RegistrationError(RuntimeError):
    def __init__(self, message: str, code: str = "registration_error") -> None:
        super().__init__(message)
        self.code = code


class QuotaExceeded(RegistrationError):
    def __init__(self, message: str = "daily registration API quota is exhausted") -> None:
        super().__init__(message, code="registration_quota_exhausted")


RegistrationLoadStats = CommonLoadStats


# Existing standalone code called this result type simply LoadStats.
LoadStats = RegistrationLoadStats


def _with_load_timestamps(
    row: Mapping[str, Any],
    previous: Mapping[str, Any] | None,
    load_now: str,
) -> Dict[str, Any]:
    """Apply loading-owned timestamps while preserving an existing creation time."""

    value = dict(row)
    previous_created_at = previous.get("created_at") if previous is not None else None
    if previous_created_at not in (None, ""):
        value["created_at"] = format_utc_datetime(previous_created_at, required=True)
    else:
        value["created_at"] = load_now
    value["updated_at"] = load_now
    return value


class RegistrationStateStore:
    """Atomic state shared by the quota ledger and period checkpoint."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> Dict[str, Any]:
        if not self.path.exists():
            return {}
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RegistrationError("registration state is unreadable", "state_unreadable") from exc
        if not isinstance(value, dict):
            raise RegistrationError("registration state must be a JSON object", "state_schema")
        return value

    def save(self, value: Mapping[str, Any]) -> None:
        atomic_write(self.path, json.dumps(dict(value), ensure_ascii=False, indent=2) + "\n")


# Compatibility name used by the standalone registration pipeline.
StateStore = RegistrationStateStore


class JsonQuotaLedger:
    """Daily local quota reservation persisted in the registration state."""

    def __init__(
        self,
        store: RegistrationStateStore,
        limit: int,
        time_zone: str = "Asia/Seoul",
    ) -> None:
        if limit <= 0:
            raise ValueError("quota limit must be greater than zero")
        self.store = store
        self.limit = limit
        self.time_zone = time_zone
        self._state = store.load()
        self._rollover_if_needed()

    def _today(self) -> str:
        today = format_utc_date(datetime.now(ZoneInfo(self.time_zone)).date(), required=True)
        assert today is not None
        return today

    def _rollover_if_needed(self) -> None:
        today = self._today()
        if self._state.get("quota_date") != today:
            self._state.update(
                {
                    "quota_date": today,
                    "used_count": 0,
                    "quota_limit": self.limit,
                    "quota_status": "AVAILABLE",
                }
            )
            self.store.save(self._state)
        else:
            self._state["quota_limit"] = self.limit

    def reserve(self) -> None:
        self._rollover_if_needed()
        used = int(self._state.get("used_count") or 0)
        if used >= self.limit:
            self._state["quota_status"] = "EXHAUSTED"
            self.store.save(self._state)
            raise QuotaExceeded()
        self._state["used_count"] = used + 1
        self._state["quota_status"] = "EXHAUSTED" if used + 1 >= self.limit else "AVAILABLE"
        self._state["last_call_at"] = utc_now_iso()
        self.store.save(self._state)

    @property
    def used_count(self) -> int:
        self._rollover_if_needed()
        return int(self._state.get("used_count") or 0)

    @property
    def remaining(self) -> int:
        return max(0, self.limit - self.used_count)


class SqlQuotaLedger:
    """Atomic quota reservation in ``api_quota_usage``."""

    API_NAME = "molit_car_registration"

    def __init__(self, settings: Settings) -> None:
        if not settings.sql_host or not settings.sql_user:
            raise RuntimeError("SQL_HOST/SQL_JDBC_URL and SQL_USER are required for SQL quota tracking")
        try:
            import pymysql  # type: ignore
        except ImportError as exc:
            raise RuntimeError("pymysql is required for SQL quota tracking") from exc
        self._client = pymysql.connect(
            host=settings.sql_host,
            port=settings.sql_port,
            user=settings.sql_user,
            password=settings.sql_password,
            database=settings.sql_database,
            charset="utf8mb4",
            autocommit=False,
        )
        self.limit = settings.registration_daily_quota
        self.time_zone = settings.time_zone

    def _today(self) -> str:
        today = format_utc_date(datetime.now(ZoneInfo(self.time_zone)).date(), required=True)
        assert today is not None
        return today

    def reserve(self) -> None:
        quota_date = self._today()
        now = to_sql_datetime(utc_now_iso())
        try:
            with self._client.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO api_quota_usage "
                    "(quota_date, api_name, quota_limit, used_count, quota_status, updated_at) "
                    "VALUES (%s, %s, %s, 0, 'AVAILABLE', %s) "
                    "ON DUPLICATE KEY UPDATE quota_limit=VALUES(quota_limit), updated_at=VALUES(updated_at)",
                    (quota_date, self.API_NAME, self.limit, now),
                )
                cursor.execute(
                    "UPDATE api_quota_usage SET used_count=used_count+1, last_call_at=%s, "
                    "updated_at=%s WHERE quota_date=%s AND api_name=%s AND used_count < quota_limit",
                    (now, now, quota_date, self.API_NAME),
                )
                if cursor.rowcount != 1:
                    self._client.rollback()
                    raise QuotaExceeded()
                cursor.execute(
                    "UPDATE api_quota_usage SET "
                    "quota_status=IF(used_count >= quota_limit, 'EXHAUSTED', 'AVAILABLE') "
                    "WHERE quota_date=%s AND api_name=%s",
                    (quota_date, self.API_NAME),
                )
            self._client.commit()
        except QuotaExceeded:
            raise
        except Exception:
            self._client.rollback()
            raise

    @property
    def used_count(self) -> int:
        with self._client.cursor() as cursor:
            cursor.execute(
                "SELECT used_count FROM api_quota_usage WHERE quota_date=%s AND api_name=%s",
                (self._today(), self.API_NAME),
            )
            row = cursor.fetchone()
        return int(row[0]) if row else 0

    @property
    def remaining(self) -> int:
        return max(0, self.limit - self.used_count)

    def close(self) -> None:
        self._client.close()


class JsonlRegistrationUpsertSink:
    """Local sink keyed by month, region, vehicle type, and usage type."""

    KEY_COLUMNS = (
        "report_month",
        "sido_name",
        "sigungu_name",
        "vehicle_type",
        "usage_type",
    )

    def __init__(self, path: Path) -> None:
        self.path = path

    @classmethod
    def _key(cls, row: Mapping[str, Any]) -> str:
        values = []
        for name in cls.KEY_COLUMNS:
            value = row.get(name)
            if value in (None, ""):
                raise ValueError(f"prepared registration row requires {name}")
            values.append(str(value))
        return "|".join(values)

    def _read(self) -> Dict[str, Dict[str, Any]]:
        rows: Dict[str, Dict[str, Any]] = {}
        if not self.path.exists():
            return rows
        try:
            lines = self.path.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            raise RegistrationError("registration JSONL output could not be read", "output_unreadable") from exc
        for index, line in enumerate(lines, start=1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise RegistrationError(
                    f"registration JSONL output is invalid at line {index}",
                    "output_schema",
                ) from exc
            if not isinstance(value, dict):
                raise RegistrationError(f"registration JSONL row is invalid at line {index}", "output_schema")
            rows[self._key(value)] = value
        return rows

    def save(self, rows: Sequence[Mapping[str, Any]]) -> RegistrationLoadStats:
        existing = self._read()
        incoming: Dict[str, Mapping[str, Any]] = {}
        for row in rows:
            incoming[self._key(row)] = row
        inserted = updated = unchanged = 0
        load_now = utc_now_iso()
        for key, row in incoming.items():
            previous = existing.get(key)
            if previous is None:
                inserted += 1
            elif previous.get("content_hash") == row.get("content_hash"):
                unchanged += 1
                continue
            else:
                updated += 1
            existing[key] = _with_load_timestamps(row, previous, load_now)
        ordered = sorted(existing.values(), key=self._key)
        atomic_write(
            self.path,
            "".join(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n" for item in ordered),
        )
        return RegistrationLoadStats(inserted, updated, unchanged)


# Compatibility name used by the standalone registration pipeline.
JsonlRegistrationSink = JsonlRegistrationUpsertSink


class SqlRegistrationUpsertSink:
    """MySQL upsert for the five-dimensional registration business key."""

    COLUMNS = (
        "report_month", "sido_name", "sigungu_name", "vehicle_type", "usage_type",
        "quantity", "source_name", "source_url", "run_id", "collected_at",
        "created_at", "updated_at", "content_hash",
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
    def _sql_value(row: Mapping[str, Any], column: str) -> Any:
        value = row.get(column)
        if column == "report_month":
            return to_sql_date(value)
        if column in {"collected_at", "created_at", "updated_at"}:
            return to_sql_datetime(format_utc_datetime(value))
        return value

    def save(self, rows: Sequence[Mapping[str, Any]]) -> RegistrationLoadStats:
        unique: Dict[str, Mapping[str, Any]] = {}
        for row in rows:
            unique[JsonlRegistrationUpsertSink._key(row)] = row
        records = list(unique.values())
        if not records:
            return RegistrationLoadStats()

        load_now = utc_now_iso()
        records = [_with_load_timestamps(row, None, load_now) for row in records]

        placeholders = ", ".join(["%s"] * len(self.COLUMNS))
        key_columns = set(JsonlRegistrationUpsertSink.KEY_COLUMNS)
        updates = ", ".join(
            f"{column}=VALUES({column})"
            for column in self.COLUMNS
            if column not in key_columns | {"created_at"}
        )
        query = (
            f"INSERT INTO vehicle_registration_reports ({', '.join(self.COLUMNS)}) "
            f"VALUES ({placeholders}) ON DUPLICATE KEY UPDATE {updates}"
        )
        values = [
            tuple(self._sql_value(row, column) for column in self.COLUMNS)
            for row in records
        ]
        predicates = " OR ".join(
            "(report_month=%s AND sido_name=%s AND sigungu_name=%s AND vehicle_type=%s AND usage_type=%s)"
            for _ in records
        )
        lookup_params: list[Any] = []
        for row in records:
            lookup_params.extend(
                [
                    to_sql_date(row.get("report_month")),
                    row.get("sido_name"),
                    row.get("sigungu_name"),
                    row.get("vehicle_type"),
                    row.get("usage_type"),
                ]
            )
        try:
            with self.connection.cursor() as cursor:
                cursor.execute(
                    "SELECT report_month, sido_name, sigungu_name, vehicle_type, usage_type, content_hash "
                    f"FROM vehicle_registration_reports WHERE {predicates}",
                    tuple(lookup_params),
                )
                previous = {
                    "|".join(str(value or "") for value in existing[:5]): existing[5]
                    for existing in cursor.fetchall()
                }
                cursor.executemany(query, values)
            self.connection.commit()
        except Exception:
            self.connection.rollback()
            raise

        inserted = updated = unchanged = 0
        for row in records:
            key = "|".join(
                str(value or "")
                for value in (
                    to_sql_date(row.get("report_month")),
                    row.get("sido_name"),
                    row.get("sigungu_name"),
                    row.get("vehicle_type"),
                    row.get("usage_type"),
                )
            )
            if key not in previous:
                inserted += 1
            elif previous[key] == row.get("content_hash"):
                unchanged += 1
            else:
                updated += 1
        return RegistrationLoadStats(inserted, updated, unchanged)

    def close(self) -> None:
        self.connection.close()


def sink_for(settings: Settings, name: str) -> Any:
    if name == "json":
        return JsonlRegistrationUpsertSink(
            settings.output_dir / "vehicle_registration_reports.jsonl"
        )
    if name == "sql":
        return SqlRegistrationUpsertSink(settings)
    raise ValueError(f"unsupported registration sink: {name}")


__all__ = [
    "JsonQuotaLedger",
    "JsonlRegistrationSink",
    "JsonlRegistrationUpsertSink",
    "LoadStats",
    "QuotaExceeded",
    "RegistrationError",
    "RegistrationLoadStats",
    "RegistrationStateStore",
    "SqlQuotaLedger",
    "SqlRegistrationUpsertSink",
    "StateStore",
    "sink_for",
]
