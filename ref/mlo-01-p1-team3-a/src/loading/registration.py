"""Registration persistence adapters, quota ledger, and resumable state."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Mapping, Sequence
from zoneinfo import ZoneInfo

from common.config import Settings
from common.sql_utils import to_sql_date, to_sql_datetime
from loading.common import atomic_write


class RegistrationError(RuntimeError):
    """A quota, state, or persistence error."""

    def __init__(self, message: str, code: str = "registration_error") -> None:
        super().__init__(message)
        self.code = code


class QuotaExceeded(RegistrationError):
    def __init__(self, message: str = "daily registration API quota is exhausted") -> None:
        super().__init__(message, code="registration_quota_exhausted")


@dataclass(frozen=True)
class RegistrationLoadStats:
    inserted_count: int = 0
    updated_count: int = 0
    unchanged_count: int = 0


class RegistrationStateStore:
    """Atomic state shared by the local quota ledger and period checkpoint."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> Dict[str, Any]:
        if not self.path.exists():
            return {}
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RegistrationError("registration state is unreadable", code="state_unreadable") from exc
        if not isinstance(value, dict):
            raise RegistrationError("registration state must be a JSON object", code="state_schema")
        return value

    def save(self, value: Mapping[str, Any]) -> None:
        atomic_write(self.path, json.dumps(dict(value), ensure_ascii=False, indent=2) + "\n")


class JsonQuotaLedger:
    """Local quota ledger; production can replace it with the SQL table atomically."""

    def __init__(self, store: RegistrationStateStore, *, limit: int, time_zone: str = "Asia/Seoul") -> None:
        self.store = store
        self.limit = limit
        self.time_zone = time_zone
        self._state = store.load()
        self._rollover_if_needed()

    def _today(self) -> str:
        return datetime.now(ZoneInfo(self.time_zone)).date().isoformat()

    def _rollover_if_needed(self) -> None:
        today = self._today()
        if self._state.get("quota_date") != today:
            self._state["quota_date"] = today
            self._state["used_count"] = 0
            self._state["quota_limit"] = self.limit
            self._state["quota_status"] = "AVAILABLE"
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
        self._state["last_call_at"] = datetime.now(timezone.utc).isoformat()
        self.store.save(self._state)

    @property
    def used_count(self) -> int:
        self._rollover_if_needed()
        return int(self._state.get("used_count") or 0)

    @property
    def remaining(self) -> int:
        return max(0, self.limit - self.used_count)


class SqlQuotaLedger:
    """Atomic daily quota reservation backed by ``api_quota_usage``."""

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
        return datetime.now(ZoneInfo(self.time_zone)).date().isoformat()

    def reserve(self) -> None:
        quota_date = self._today()
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
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
                    "UPDATE api_quota_usage SET quota_status=IF(used_count >= quota_limit, 'EXHAUSTED', 'AVAILABLE') "
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
    """Deterministic local sink with the same normalized business key as SQL."""

    def __init__(self, path: Path) -> None:
        self.path = path

    @staticmethod
    def _key(row: Mapping[str, Any]) -> str:
        return "|".join(
            str(row.get(name) or "")
            for name in ("report_month", "sido_name", "sigungu_name", "vehicle_type", "usage_type")
        )

    def _read(self) -> Dict[str, Dict[str, Any]]:
        rows: Dict[str, Dict[str, Any]] = {}
        if not self.path.exists():
            return rows
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            value = json.loads(line)
            if isinstance(value, dict):
                rows[self._key(value)] = value
        return rows

    def save(self, rows: Sequence[Mapping[str, Any]]) -> RegistrationLoadStats:
        existing = self._read()
        inserted = updated = unchanged = 0
        for row in rows:
            key = self._key(row)
            previous = existing.get(key)
            if previous is None:
                inserted += 1
            elif previous.get("content_hash") == row.get("content_hash"):
                unchanged += 1
            else:
                updated += 1
            existing[key] = dict(row)
        ordered = sorted(existing.values(), key=self._key)
        atomic_write(
            self.path,
            "".join(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n" for item in ordered),
        )
        return RegistrationLoadStats(inserted, updated, unchanged)


class SqlRegistrationUpsertSink:
    """MySQL-compatible writer for the normalized registration-report table."""

    COLUMNS = (
        "report_month", "sido_name", "sigungu_name", "vehicle_type", "usage_type", "quantity", "source_name",
        "source_url", "run_id", "collected_at", "created_at", "updated_at", "content_hash",
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

    def save(self, rows: Sequence[Mapping[str, Any]]) -> RegistrationLoadStats:
        if not rows:
            return RegistrationLoadStats()
        placeholders = ", ".join(["%s"] * len(self.COLUMNS))
        updates = ", ".join(
            f"{column}=VALUES({column})"
            for column in self.COLUMNS
            if column
            not in {"report_month", "sido_name", "sigungu_name", "vehicle_type", "usage_type", "created_at"}
        )
        query = (
            f"INSERT INTO vehicle_registration_reports ({', '.join(self.COLUMNS)}) "
            f"VALUES ({placeholders}) ON DUPLICATE KEY UPDATE {updates}"
        )

        def sql_value(row: Mapping[str, Any], column: str) -> Any:
            value = row.get(column)
            if column == "report_month":
                return to_sql_date(value)
            if column in {"collected_at", "created_at", "updated_at"}:
                return to_sql_datetime(value)
            return value

        values = [tuple(sql_value(row, column) for column in self.COLUMNS) for row in rows]
        try:
            with self.connection.cursor() as cursor:
                predicates = " OR ".join(
                    "(report_month=%s AND sido_name=%s AND sigungu_name=%s AND vehicle_type=%s AND usage_type=%s)"
                    for _ in rows
                )
                lookup_params = []
                for row in rows:
                    lookup_params.extend(
                        [
                            to_sql_date(row.get("report_month")),
                            row.get("sido_name"),
                            row.get("sigungu_name"),
                            row.get("vehicle_type"),
                            row.get("usage_type"),
                        ]
                    )
                cursor.execute(
                    "SELECT report_month, sido_name, sigungu_name, vehicle_type, usage_type, content_hash "
                    f"FROM vehicle_registration_reports WHERE {predicates}",
                    tuple(lookup_params),
                )
                previous: Dict[str, Any] = {}
                for existing_row in cursor.fetchall():
                    previous["|".join(str(value or "") for value in existing_row[:5])] = existing_row[5]
                cursor.executemany(query, values)
            self.connection.commit()
        except Exception:
            self.connection.rollback()
            raise
        inserted = updated = unchanged = 0
        for row in rows:
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
