"""FAQ JSONL/MongoDB persistence adapters."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Mapping, Sequence

from common.config import Settings
from common.contracts import LoadStats

from .common import atomic_write


FaqLoadStats = LoadStats


class JsonlFaqUpsertSink:
    """Local, deterministic FAQ sink using ``faq_id`` as the business key."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def _read(self) -> Dict[str, Dict[str, Any]]:
        rows: Dict[str, Dict[str, Any]] = {}
        if not self.path.exists():
            return rows
        try:
            lines = self.path.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            raise RuntimeError("FAQ JSONL output could not be read") from exc
        for index, line in enumerate(lines, start=1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise RuntimeError(f"FAQ JSONL output is invalid at line {index}") from exc
            if not isinstance(value, dict) or value.get("faq_id") in (None, ""):
                raise RuntimeError(f"FAQ JSONL record is invalid at line {index}")
            rows[str(value["faq_id"])] = value
        return rows

    def save(self, documents: Sequence[Mapping[str, Any]]) -> FaqLoadStats:
        existing = self._read()
        inserted = updated = unchanged = 0
        for document in documents:
            if document.get("faq_id") in (None, ""):
                raise ValueError("prepared FAQ document requires faq_id")
            key = str(document["faq_id"])
            previous = existing.get(key)
            if previous is None:
                inserted += 1
            elif previous.get("content_hash") == document.get("content_hash"):
                unchanged += 1
            else:
                updated += 1
            existing[key] = dict(document)
        ordered = sorted(existing.values(), key=lambda item: str(item["faq_id"]))
        atomic_write(
            self.path,
            "".join(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n" for item in ordered),
        )
        return FaqLoadStats(inserted, updated, unchanged)


class MongoFaqUpsertSink:
    """MongoDB FAQ upsert; MongoDB is imported only for the selected sink."""

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
            if document.get("faq_id") in (None, ""):
                raise ValueError("prepared FAQ document requires faq_id")
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


__all__ = ["FaqLoadStats", "JsonlFaqUpsertSink", "MongoFaqUpsertSink"]
