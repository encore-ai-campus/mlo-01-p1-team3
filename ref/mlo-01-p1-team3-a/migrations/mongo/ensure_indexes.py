"""Create the non-destructive MongoDB FAQ migration for the MVP.

Usage on the Backend host:

    python migrations/mongo/ensure_indexes.py

The script creates the FAQ collection if it does not exist and ensures the
indexes required by the data contract.  It never drops a collection or index;
future validator changes must be made as an explicit forward migration.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from common.config import settings_from_env


def ensure_indexes(
    *,
    uri: str,
    database: str = "support_db",
    collection: str = "faq",
    server_selection_timeout_ms: int = 5000,
) -> dict[str, Any]:
    if not uri:
        raise ValueError("MONGODB_URI is required")
    try:
        from pymongo import ASCENDING, DESCENDING, MongoClient  # type: ignore
    except ImportError as exc:
        raise RuntimeError("pymongo is required to run the MongoDB migration") from exc

    client = MongoClient(
        uri,
        serverSelectionTimeoutMS=server_selection_timeout_ms,
        tz_aware=True,
    )
    try:
        db = client[database]
        names = db.list_collection_names()
        if collection not in names:
            db.create_collection(
                collection,
                validator={
                    "$jsonSchema": {
                        "bsonType": "object",
                        "required": [
                            "faq_id",
                            "question",
                            "answer",
                            "brand",
                            "category",
                            "source_url",
                            "license",
                            "attribution",
                            "content_hash",
                            "is_active",
                            "run_id",
                            "collected_at",
                            "created_at",
                            "updated_at",
                        ],
                        "properties": {
                            "faq_id": {"bsonType": "string"},
                            "question": {"bsonType": "string"},
                            "answer": {"bsonType": "string"},
                            "brand": {"bsonType": "string"},
                            "category": {"bsonType": "string"},
                            "source_url": {"bsonType": "string"},
                            "license": {"bsonType": "string"},
                            "attribution": {"bsonType": "string"},
                            "content_hash": {"bsonType": "string"},
                            "is_active": {"bsonType": "bool"},
                            "run_id": {"bsonType": "string"},
                        },
                    }
                },
                validationLevel="strict",
                validationAction="error",
            )
        coll = db[collection]
        indexes = {
            "uq_faq_id": coll.create_index(
                [("faq_id", ASCENDING)], unique=True, name="uq_faq_id"
            ),
            "ix_faq_brand_category": coll.create_index(
                [("brand", ASCENDING), ("category", ASCENDING)], name="ix_faq_brand_category"
            ),
            "ix_faq_updated_at": coll.create_index(
                [("updated_at", DESCENDING)], name="ix_faq_updated_at"
            ),
        }
        client.admin.command("ping")
        return {"status": "OK", "database": database, "collection": collection, "indexes": indexes}
    finally:
        client.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ensure MongoDB FAQ indexes")
    parser.add_argument("--uri")
    parser.add_argument("--database")
    parser.add_argument("--collection")
    parser.add_argument("--timeout-ms", type=int)
    args = parser.parse_args(argv)
    try:
        import json

        settings = settings_from_env()
        print(json.dumps(ensure_indexes(
            uri=args.uri or settings.mongo_uri,
            database=args.database or settings.mongo_database,
            collection=args.collection or settings.mongo_collection,
            server_selection_timeout_ms=args.timeout_ms or settings.mongo_server_selection_timeout_ms,
        ), ensure_ascii=False))
        return 0
    except Exception:
        print(json.dumps({"status": "FAILED", "error_code": "mongo_migration_failed"}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
