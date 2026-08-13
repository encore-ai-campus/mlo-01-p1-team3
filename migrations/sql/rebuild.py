"""Destructively rebuild the configured application MySQL schema.

This operator-only entry point requires an exact database-name confirmation.
It drops tables only from the configured data database, then applies the
existing forward migrations.  MySQL system schemas are always rejected.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from common.config import settings_from_env
from migrations.sql.run import apply


SYSTEM_DATABASES = {
    "information_schema",
    "mysql",
    "performance_schema",
    "sys",
}
MIGRATION_DATABASE = "sales_support_db"
IDENTIFIER_PATTERN = re.compile(r"[A-Za-z0-9_]+")


def _validated_database(name: str) -> str:
    if name.lower() in SYSTEM_DATABASES:
        raise ValueError(f"refusing to rebuild MySQL system database: {name}")
    if not IDENTIFIER_PATTERN.fullmatch(name):
        raise ValueError(f"unsafe MySQL database identifier: {name!r}")
    if name != MIGRATION_DATABASE:
        raise ValueError(
            f"configured database does not match the migration target: {name}"
        )
    return name


def drop_application_tables(
    *,
    host: str,
    port: int,
    user: str,
    password: str | None,
    data_database: str,
) -> list[str]:
    """Drop every base table in the explicitly configured app schema."""

    try:
        import pymysql  # type: ignore
    except ImportError as exc:
        raise RuntimeError("pymysql is required to rebuild SQL schemas") from exc

    database = _validated_database(data_database)
    connection = pymysql.connect(
        host=host,
        port=port,
        user=user,
        password=password,
        charset="utf8mb4",
        autocommit=True,
    )
    dropped: list[str] = []
    try:
        with connection.cursor() as cursor:
            cursor.execute("SET FOREIGN_KEY_CHECKS = 0")
            try:
                cursor.execute(
                    "SELECT TABLE_NAME FROM information_schema.TABLES "
                    "WHERE TABLE_SCHEMA=%s AND TABLE_TYPE='BASE TABLE' "
                    "ORDER BY TABLE_NAME",
                    (database,),
                )
                tables = [str(row[0]) for row in cursor.fetchall()]
                for table in tables:
                    if not IDENTIFIER_PATTERN.fullmatch(table):
                        raise ValueError(f"unsafe MySQL table identifier: {table!r}")
                    cursor.execute(f"DROP TABLE `{database}`.`{table}`")
                    dropped.append(table)
            finally:
                cursor.execute("SET FOREIGN_KEY_CHECKS = 1")
        return dropped
    finally:
        connection.close()


def rebuild(
    directory: Path,
    *,
    host: str,
    port: int,
    user: str,
    password: str | None,
    data_database: str,
) -> dict[str, Any]:
    dropped = drop_application_tables(
        host=host,
        port=port,
        user=user,
        password=password,
        data_database=data_database,
    )
    migration = apply(
        directory,
        host=host,
        port=port,
        user=user,
        password=password,
    )
    return {"status": "OK", "dropped": dropped, "migration": migration}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Drop configured app tables and reapply SQL migrations"
    )
    parser.add_argument("--directory", type=Path, default=Path(__file__).parent)
    parser.add_argument("--confirm-data-database", required=True)
    args = parser.parse_args(argv)
    try:
        settings = settings_from_env()
        if args.confirm_data_database != settings.sql_database:
            raise ValueError("data database confirmation does not match Settings")
        if not settings.sql_host or not settings.sql_user:
            raise ValueError("SQL host and user are required")
        result = rebuild(
            args.directory,
            host=settings.sql_host,
            port=settings.sql_port,
            user=settings.sql_user,
            password=settings.sql_password,
            data_database=settings.sql_database,
        )
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except Exception:
        print(
            json.dumps(
                {"status": "FAILED", "error_code": "sql_rebuild_failed"}
            ),
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
