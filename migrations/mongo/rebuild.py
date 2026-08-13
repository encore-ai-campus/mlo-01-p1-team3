"""Destructively rebuild the configured application MongoDB database.

The command requires an exact database-name confirmation, drops every
non-system collection in that configured database, then recreates the FAQ
validator and indexes through the canonical Mongo migration.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from common.config import settings_from_env
from migrations.mongo.ensure_indexes import ensure_indexes


SYSTEM_DATABASES = {"admin", "config", "local"}


def drop_application_collections(
    *,
    uri: str,
    database: str,
    server_selection_timeout_ms: int,
) -> list[str]:
    """Drop every non-system collection in one configured app database."""

    if database.lower() in SYSTEM_DATABASES:
        raise ValueError(f"refusing to rebuild MongoDB system database: {database}")
    if not database.strip():
        raise ValueError("MongoDB database is required")
    try:
        from pymongo import MongoClient  # type: ignore
    except ImportError as exc:
        raise RuntimeError("pymongo is required to rebuild MongoDB") from exc

    client = MongoClient(
        uri,
        serverSelectionTimeoutMS=server_selection_timeout_ms,
        tz_aware=True,
    )
    dropped: list[str] = []
    try:
        client.admin.command("ping")
        selected = client[database]
        for collection in sorted(selected.list_collection_names()):
            if collection.startswith("system."):
                continue
            selected.drop_collection(collection)
            dropped.append(collection)
        return dropped
    finally:
        client.close()


def rebuild(
    *,
    uri: str,
    database: str,
    collection: str,
    server_selection_timeout_ms: int,
) -> dict[str, Any]:
    dropped = drop_application_collections(
        uri=uri,
        database=database,
        server_selection_timeout_ms=server_selection_timeout_ms,
    )
    migration = ensure_indexes(
        uri=uri,
        database=database,
        collection=collection,
        server_selection_timeout_ms=server_selection_timeout_ms,
    )
    return {"status": "OK", "dropped": dropped, "migration": migration}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Drop configured app collections and reapply Mongo migration"
    )
    parser.add_argument("--confirm-database", required=True)
    args = parser.parse_args(argv)
    try:
        settings = settings_from_env()
        if args.confirm_database != settings.mongo_database:
            raise ValueError("MongoDB database confirmation does not match Settings")
        result = rebuild(
            uri=settings.mongo_uri,
            database=settings.mongo_database,
            collection=settings.mongo_collection,
            server_selection_timeout_ms=settings.mongo_server_selection_timeout_ms,
        )
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except Exception:
        print(
            json.dumps(
                {"status": "FAILED", "error_code": "mongo_rebuild_failed"}
            ),
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
