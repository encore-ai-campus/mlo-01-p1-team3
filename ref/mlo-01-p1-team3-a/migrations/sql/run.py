"""Apply forward SQL migrations without destructive rollback."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Iterable, List, Optional

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from common.config import settings_from_env


def split_sql(script: str) -> List[str]:
    """Split the simple migration grammar while respecting quoted strings."""

    statements: List[str] = []
    buffer: List[str] = []
    quote: str | None = None
    for char in script:
        if quote:
            buffer.append(char)
            if char == quote:
                quote = None
            continue
        if char in {"'", '"', "`"}:
            quote = char
            buffer.append(char)
        elif char == ";":
            statement = "".join(buffer).strip()
            if statement:
                statements.append(statement)
            buffer = []
        else:
            buffer.append(char)
    statement = "".join(buffer).strip()
    if statement:
        statements.append(statement)
    return statements


def migration_files(directory: Path) -> Iterable[Path]:
    return sorted(directory.glob("V*__*.sql"))


def apply(
    directory: Path,
    *,
    host: str,
    port: int,
    user: str,
    password: Optional[str],
) -> dict[str, object]:
    try:
        import pymysql  # type: ignore
    except ImportError as exc:
        raise RuntimeError("pymysql is required to run SQL migrations") from exc
    connection = pymysql.connect(
        host=host,
        port=port,
        user=user,
        password=password,
        charset="utf8mb4",
        autocommit=False,
    )
    applied_versions: List[str] = []
    try:
        with connection.cursor() as cursor:
            try:
                cursor.execute("SELECT version, checksum FROM sales_support_db.schema_migrations")
                applied = {str(version): str(checksum) for version, checksum in cursor.fetchall()}
            except Exception:
                applied = {}
        for path in migration_files(directory):
            version = path.name.split("__", 1)[0]
            checksum = hashlib.sha256(path.read_bytes()).hexdigest()
            if version in applied:
                if applied[version] != checksum:
                    raise RuntimeError(f"migration checksum mismatch: {version}")
                continue
            script = path.read_text(encoding="utf-8")
            with connection.cursor() as cursor:
                for statement in split_sql(script):
                    cursor.execute(statement)
                cursor.execute(
                    "INSERT INTO sales_support_db.schema_migrations (version, checksum, applied_at) "
                    "VALUES (%s, %s, UTC_TIMESTAMP())",
                    (version, checksum),
                )
            connection.commit()
            applied_versions.append(version)
            applied[version] = checksum
        return {"status": "OK", "applied": applied_versions}
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Apply MLO SQL forward migrations")
    parser.add_argument("--directory", type=Path, default=Path(__file__).parent)
    parser.add_argument("--host")
    parser.add_argument("--port", type=int)
    parser.add_argument("--user")
    parser.add_argument("--password")
    args = parser.parse_args(argv)
    try:
        settings = settings_from_env()
    except (RuntimeError, ValueError) as exc:
        print(json.dumps({"status": "FAILED", "error_code": "invalid_environment"}), file=sys.stderr)
        return 1
    host = args.host if args.host is not None else settings.sql_host
    port = args.port if args.port is not None else settings.sql_port
    user = args.user if args.user is not None else settings.sql_user
    password = args.password if args.password is not None else settings.sql_password
    if not host or not user:
        print(json.dumps({"status": "FAILED", "error_code": "missing_sql_host_or_user"}), file=sys.stderr)
        return 1
    try:
        print(json.dumps(apply(args.directory, host=host, port=port, user=user, password=password), ensure_ascii=False))
        return 0
    except Exception:
        print(json.dumps({"status": "FAILED", "error_code": "sql_migration_failed"}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
