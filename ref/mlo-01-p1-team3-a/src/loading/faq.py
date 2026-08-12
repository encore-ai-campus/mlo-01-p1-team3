"""FAQ persistence adapters: MongoDB upsert and deterministic JSONL sink."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Mapping, Sequence

from common.config import Settings
from loading.common import atomic_write


@dataclass(frozen=True)
class FaqLoadStats:
    inserted_count: int = 0
    updated_count: int = 0
    unchanged_count: int = 0


class JsonlFaqUpsertSink:
    """A deterministic local substitute for MongoDB FAQ upsert tests."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def _read(self) -> Dict[str, Dict[str, Any]]:
        rows: Dict[str, Dict[str, Any]] = {}
        if not self.path.exists():
            return rows
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            value = json.loads(line)
            if isinstance(value, dict) and value.get("faq_id") is not None:
                rows[str(value["faq_id"])] = value
        return rows

    def save(self, documents: Sequence[Mapping[str, Any]]) -> FaqLoadStats:
        existing = self._read()
        inserted = updated = unchanged = 0
        for document in documents:
            key = str(document["faq_id"])
            previous = existing.get(key)
            if previous is None:
                inserted += 1
            elif previous.get("content_hash") == document.get("content_hash"):
                unchanged += 1
            else:
                updated += 1
            existing[key] = dict(document)
        ordered = sorted(existing.values(), key=lambda item: str(item.get("faq_id")))
        atomic_write(
            self.path,
            "".join(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n" for item in ordered),
        )
        return FaqLoadStats(inserted, updated, unchanged)


class MongoFaqUpsertSink:
    """MongoDB FAQ upsert using the migration-created indexes."""

    def __init__(self, settings: Settings) -> None:
        if not settings.mongo_uri:
            raise RuntimeError("MONGODB_URI is required for --sink mongo")
        try:
            from pymongo import MongoClient  # type: ignore
        except ImportError as exc:
            raise RuntimeError("pymongo is required for --sink mongo") from exc
        self._client = MongoClient(
            settings.mongo_uri,
            serverSelectionTimeoutMS=settings.mongo_server_selection_timeout_ms,
            tz_aware=True,
        )
        self._collection = self._client[settings.mongo_database][settings.mongo_collection]
        self._collection.create_index("faq_id", unique=True, name="uq_faq_id")
        self._collection.create_index([("brand", 1), ("category", 1)], name="ix_faq_brand_category")
        self._collection.create_index([("updated_at", -1)], name="ix_faq_updated_at")

    def save(self, documents: Sequence[Mapping[str, Any]]) -> FaqLoadStats:
        inserted = updated = unchanged = 0
        for document in documents:
            key = str(document["faq_id"])
            previous = self._collection.find_one({"faq_id": key}, {"content_hash": 1})
            if previous is None:
                inserted += 1
            elif previous.get("content_hash") == document.get("content_hash"):
                unchanged += 1
            else:
                updated += 1
            mutable = dict(document)
            created_at = mutable.pop("created_at", None)
            self._collection.update_one(
                {"faq_id": key},
                {"$set": mutable, "$setOnInsert": {"created_at": created_at}},
                upsert=True,
            )
        return FaqLoadStats(inserted, updated, unchanged)

    def close(self) -> None:
        self._client.close()
