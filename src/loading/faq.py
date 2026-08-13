"""FAQ JSONL/MongoDB persistence adapters."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Mapping, Sequence
from urllib.parse import urlsplit

from common.config import Settings
from common.contracts import LoadStats
from common.time_utils import format_utc_datetime, to_utc_datetime, utc_now_iso

from .common import atomic_write


FaqLoadStats = LoadStats


_FAQ_REQUIRED_TEXT_FIELDS = (
    "faq_id",
    "question",
    "answer",
    "brand",
    "category",
    "license",
    "attribution",
    "content_hash",
    "run_id",
)
_MONGO_DATE_FIELDS = ("source_updated_at", "collected_at", "created_at", "updated_at")


def _validate_faq_document(document: Mapping[str, Any]) -> None:
    """Validate the prepared FAQ contract before JSONL or Mongo persistence."""

    if not isinstance(document, Mapping):
        raise ValueError("prepared FAQ document must be an object")
    for name in _FAQ_REQUIRED_TEXT_FIELDS:
        value = document.get(name)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"prepared FAQ document requires non-empty {name}")

    source_url = document.get("source_url")
    if not isinstance(source_url, str) or not source_url.strip():
        raise ValueError("prepared FAQ document requires source_url")
    parsed_url = urlsplit(source_url)
    if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
        raise ValueError("prepared FAQ source_url must be an absolute HTTP(S) URL")

    if not isinstance(document.get("is_active"), bool):
        raise ValueError("prepared FAQ document requires boolean is_active")
    for name in ("source_updated_at", "collected_at"):
        try:
            format_utc_datetime(document.get(name), required=True)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"prepared FAQ document requires valid {name}") from exc


def _with_load_timestamps(
    document: Mapping[str, Any],
    previous: Mapping[str, Any] | None,
    load_now: str,
) -> Dict[str, Any]:
    """Apply loading-owned timestamps while preserving an existing creation time."""

    value = dict(document)
    previous_created_at = previous.get("created_at") if previous is not None else None
    if previous_created_at not in (None, ""):
        value["created_at"] = format_utc_datetime(previous_created_at, required=True)
    else:
        value["created_at"] = load_now
    value["updated_at"] = load_now
    return value


def _as_mongo_document(
    document: Mapping[str, Any],
    previous: Mapping[str, Any] | None,
    load_now: str,
) -> Dict[str, Any]:
    """Convert the prepared FAQ and load timestamps to MongoDB date values."""

    value = _with_load_timestamps(document, previous, load_now)
    for name in _MONGO_DATE_FIELDS:
        normalized = to_utc_datetime(value.get(name), required=True)
        assert normalized is not None
        value[name] = normalized
    return value


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
            try:
                _validate_faq_document(value)
            except ValueError as exc:
                raise RuntimeError(f"FAQ JSONL record is invalid at line {index}") from exc
            rows[str(value["faq_id"])] = value
        return rows

    def save(self, documents: Sequence[Mapping[str, Any]]) -> FaqLoadStats:
        existing = self._read()
        inserted = updated = unchanged = 0
        load_now = utc_now_iso()
        for document in documents:
            _validate_faq_document(document)
            key = str(document["faq_id"])
            previous = existing.get(key)
            if previous is None:
                inserted += 1
            elif previous.get("content_hash") == document.get("content_hash"):
                unchanged += 1
                continue
            else:
                updated += 1
            existing[key] = _with_load_timestamps(document, previous, load_now)
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
        self._database = self._client[settings.mongo_database]
        self._collection = self._database[settings.mongo_collection]
        self._ensure_validator(settings.mongo_collection)
        self._collection.create_index("faq_id", unique=True, name="uq_faq_id")
        self._collection.create_index([("brand", 1), ("category", 1)], name="ix_faq_brand_category")
        self._collection.create_index([("updated_at", -1)], name="ix_faq_updated_at")

    def _ensure_validator(self, collection_name: str) -> None:
        """Require the explicit Mongo migration before accepting documents."""

        if collection_name not in self._database.list_collection_names():
            raise RuntimeError(
                "MongoDB FAQ migration must create the collection validator before loading"
            )
        definitions = self._database.list_collections(filter={"name": collection_name})
        definition = next(iter(definitions), None)
        options = definition.get("options", {}) if isinstance(definition, Mapping) else {}
        validator = options.get("validator") if isinstance(options, Mapping) else None
        schema = validator.get("$jsonSchema") if isinstance(validator, Mapping) else None
        properties = schema.get("properties") if isinstance(schema, Mapping) else None
        if not isinstance(properties, Mapping) or any(
            not isinstance(properties.get(name), Mapping)
            or properties[name].get("bsonType") != "date"
            for name in _MONGO_DATE_FIELDS
        ):
            raise RuntimeError(
                "MongoDB FAQ collection validator must define BSON Date timestamps"
            )

    def save(self, documents: Sequence[Mapping[str, Any]]) -> FaqLoadStats:
        inserted = updated = unchanged = 0
        load_now = utc_now_iso()
        for document in documents:
            _validate_faq_document(document)
            key = str(document["faq_id"])
            previous = self._collection.find_one(
                {"faq_id": key},
                {"content_hash": 1, "created_at": 1},
            )
            if previous is None:
                inserted += 1
            elif previous.get("content_hash") == document.get("content_hash"):
                unchanged += 1
                continue
            else:
                updated += 1
            mutable = _as_mongo_document(document, previous, load_now)
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
