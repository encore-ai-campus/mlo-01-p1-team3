"""MongoDB Replica Set에 FAQ 문서를 안전하게 UPSERT한다."""

from datetime import datetime, timezone
from typing import Any

from pymongo import ASCENDING, MongoClient

from config import Settings
from models import LoadStats


# ============================================================================
# MONGODB STORE START: Replica Set URI 연결, 인덱스, FAQ UPSERT를 처리한다.
# ============================================================================


FAQ_COMPARE_FIELDS = ("faq_id", "brand", "brand_code", "category", "question", "answer", "source_url", "reviewed_at", "crawl_url")


def connect_mongodb(settings: Settings) -> MongoClient:
    """Replica Set 전체 URI로 연결해 현재 Primary를 자동 선택한다."""
    if not settings.mongo_uri:
        raise ValueError("MONGO_URI must be configured with all Replica Set members")
    if "replicaSet=" not in settings.mongo_uri:
        raise ValueError("MONGO_URI must include replicaSet=<replica-set-name>")
    client = MongoClient(settings.mongo_uri, serverSelectionTimeoutMS=5000, retryWrites=True, w="majority")
    client.admin.command("ping")
    return client


def create_indexes(collection: Any) -> None:
    """FAQ ID 중복 방지와 조회 성능을 위한 인덱스를 보장한다."""
    collection.create_index([("faq_id", ASCENDING)], unique=True, name="uq_faq_id")
    collection.create_index([("brand", ASCENDING)], name="idx_faq_brand")
    collection.create_index([("category", ASCENDING)], name="idx_faq_category")


def load_faqs(client: MongoClient, settings: Settings, faqs: list[dict[str, Any]]) -> LoadStats:
    """faq_id 기준으로 신규·수정 FAQ만 MongoDB Primary에 UPSERT한다."""
    collection = client[settings.mongo_database][settings.mongo_faq_collection]
    create_indexes(collection)
    stats = LoadStats()
    for faq in faqs:
        existing = collection.find_one({"faq_id": faq["faq_id"]}, {field: 1 for field in FAQ_COMPARE_FIELDS})
        if existing:
            changed = any(existing.get(field) != faq.get(field) for field in FAQ_COMPARE_FIELDS)
            if not changed:
                stats.unchanged += 1
                continue
            collection.update_one({"_id": existing["_id"]}, {"$set": {**faq, "updated_at": datetime.now(timezone.utc)}})
            stats.updated += 1
            continue
        now = datetime.now(timezone.utc)
        result = collection.update_one({"faq_id": faq["faq_id"]}, {"$set": {**faq, "updated_at": now}, "$setOnInsert": {"created_at": now}}, upsert=True)
        if result.upserted_id is not None:
            stats.inserted += 1
        else:
            stats.unchanged += 1
    return stats


# ============================================================================
# MONGODB STORE END: Replica Set 적재 기능의 끝.
# ============================================================================
