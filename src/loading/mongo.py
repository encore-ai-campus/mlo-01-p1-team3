"""원본 FAQ MongoDB 연결, 인덱스, Upsert."""

from datetime import datetime, timezone

from pymongo import ASCENDING, MongoClient

from common.config import MONGO_COLLECTION, MONGO_DATABASE, MONGO_URI


FAQ_COMPARE_FIELDS = (
    "faq_id", "brand", "brand_code", "category", "question", "answer",
    "source_url", "reviewed_at", "crawl_url",
)


# =============================================================================
# [FAQ MongoDB 적재 시작] 연결 및 인덱스 생성
# 기능: 원본 MongoDB 연결을 확인하고 faq_id unique, brand/category 인덱스를 준비한다.
# 원본 위치: load_faqs_mongodb.py의 get_mongo_collection(), create_indexes()
# =============================================================================
def get_mongo_collection():
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    client.admin.command("ping")
    collection = client[MONGO_DATABASE][MONGO_COLLECTION]
    print("[MONGO] 연결 완료")
    return client, collection


def create_indexes(collection):
    collection.create_index([("faq_id", ASCENDING)], unique=True, name="uq_faq_id")
    collection.create_index([("brand", ASCENDING)], name="idx_brand")
    collection.create_index([("category", ASCENDING)], name="idx_category")
    print("[MONGO] 인덱스 확인 완료")
# =============================================================================
# [FAQ MongoDB 적재 끝]
# =============================================================================


# =============================================================================
# [FAQ MongoDB 적재 시작] faq_id 기준 신규·수정·변경없음 Upsert
# 기능: 비교 대상 필드가 바뀐 경우에만 updated_at을 변경한다.
# 원본 위치: load_faqs_mongodb.py의 upsert_faq()
# =============================================================================
def upsert_faq(collection, faq):
    existing = collection.find_one(
        {"faq_id": faq["faq_id"]},
        {field: 1 for field in FAQ_COMPARE_FIELDS},
    )

    if existing is not None:
        changed = any(existing.get(field) != faq.get(field) for field in FAQ_COMPARE_FIELDS)
        if not changed:
            return "unchanged"

        collection.update_one(
            {"_id": existing["_id"]},
            {"$set": {**faq, "updated_at": datetime.now(timezone.utc)}},
        )
        return "updated"

    now = datetime.now(timezone.utc)
    result = collection.update_one(
        {"faq_id": faq["faq_id"]},
        {"$set": {**faq, "updated_at": now}, "$setOnInsert": {"created_at": now}},
        upsert=True,
    )
    return "inserted" if result.upserted_id is not None else "unchanged"
# =============================================================================
# [FAQ MongoDB 적재 끝]
# =============================================================================
