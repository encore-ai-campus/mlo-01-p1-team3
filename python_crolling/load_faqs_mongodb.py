import os
import time
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from pymongo import ASCENDING, MongoClient


load_dotenv()


# =========================================================
# 기본 설정 (.env 구조 유지)
# =========================================================

BASE_URL = "http://192.168.0.51:4000"
FAQ_URL = f"{BASE_URL}/faqs"

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DATABASE = os.getenv("MONGO_DATABASE", "car_data")
MONGO_COLLECTION = os.getenv("MONGO_COLLECTION", "faqs")

# 5분
INTERVAL_SECONDS = 300

# 이 필드들만 비교합니다. created_at/updated_at은 비교 대상에서 제외해야
# 내용이 같을 때 매번 수정되는 것을 막을 수 있습니다.
FAQ_COMPARE_FIELDS = (
    "faq_id",
    "brand",
    "brand_code",
    "category",
    "question",
    "answer",
    "source_url",
    "reviewed_at",
    "crawl_url",
)


# =========================================================
# 1. FAQ 페이지 요청 및 파싱
# =========================================================

def get_faq_page():
    print(f"[FETCH] {FAQ_URL}")
    response = requests.get(FAQ_URL, timeout=15)
    response.raise_for_status()
    return response.text


def get_text_or_default(item, selector, default=None):
    element = item.select_one(selector)
    return element.get_text(" ", strip=True) if element else default


def crawl_faqs():
    soup = BeautifulSoup(get_faq_page(), "html.parser")
    faq_items = soup.select("article.faq-item")
    print(f"[CRAWL] FAQ 항목 {len(faq_items)}개 발견")

    raw_faqs = []
    for item in faq_items:
        faq_id = item.get("data-faq-id")
        source_url = item.get("data-source-url")
        reviewed_at = item.get("data-reviewed-at")
        brand_code = item.get("data-brand")
        category_code = item.get("data-category")

        brand = get_text_or_default(item, '[data-field="brand"]', brand_code)
        category = get_text_or_default(item, '[data-field="category"]', category_code)
        question = get_text_or_default(item, '[data-field="question"]')
        answer = get_text_or_default(item, '[data-field="answer"]')

        if not faq_id:
            print("[SKIP] faq_id 없음")
            continue
        if not question:
            print(f"[SKIP] {faq_id}: question 없음")
            continue
        if not answer:
            print(f"[SKIP] {faq_id}: answer 없음")
            continue

        raw_faqs.append({
            "faq_id": faq_id,
            "brand": brand,
            "brand_code": brand_code,
            "category": category,
            "question": question,
            "answer": answer,
            "source_url": source_url,
            "reviewed_at": reviewed_at,
            "crawl_url": FAQ_URL,
        })

    print(f"[CRAWL] 정상 파싱 {len(raw_faqs)}개")
    return raw_faqs


# =========================================================
# 2. MongoDB 연결 및 인덱스 (기존 구조 유지)
# =========================================================

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


# =========================================================
# 3. faq_id 기준 UPSERT
# =========================================================

def upsert_faq(collection, faq):
    """신규/실제수정/변경없음 중 하나를 반환합니다."""
    existing = collection.find_one(
        {"faq_id": faq["faq_id"]},
        {field: 1 for field in FAQ_COMPARE_FIELDS},
    )

    if existing is not None:
        changed = any(
            existing.get(field) != faq.get(field)
            for field in FAQ_COMPARE_FIELDS
        )
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
        {
            "$set": {**faq, "updated_at": now},
            "$setOnInsert": {"created_at": now},
        },
        upsert=True,
    )
    return "inserted" if result.upserted_id is not None else "unchanged"


# =========================================================
# 4. 1회 실행
# =========================================================

def run_once(collection):
    fetched = inserted = updated = unchanged = failed = 0

    try:
        raw_faqs = crawl_faqs()
        fetched = len(raw_faqs)

        for index, faq in enumerate(raw_faqs, start=1):
            try:
                result = upsert_faq(collection, faq)
                if result == "inserted":
                    inserted += 1
                elif result == "updated":
                    updated += 1
                else:
                    unchanged += 1

                print(f"[{index}/{fetched}] {faq['faq_id']} | {faq['brand']} | {result}")
                time.sleep(0.05)
            except Exception as exc:
                failed += 1
                print(f"[ERROR] {faq.get('faq_id')} {exc}")
    except Exception as exc:
        failed += 1
        print(f"[FATAL ERROR] {exc}")

    print("\n==========================")
    print("FAQ MongoDB 반영 결과")
    print("==========================")
    print(f"수집: {fetched}")
    print(f"신규: {inserted}")
    print(f"실제수정: {updated}")
    print(f"변경없음: {unchanged}")
    print(f"실패: {failed}")


# =========================================================
# 5. MAIN - Ctrl+C로 종료 가능한 5분 주기 실행
# =========================================================

def main():
    client = None
    try:
        print("\n==========================")
        print("FAQ 5분 주기 최신화 시작")
        print("종료하려면 Ctrl+C를 누르세요.")
        print("==========================")

        client, collection = get_mongo_collection()
        create_indexes(collection)

        while True:
            print(f"\n[RUN] {datetime.now().isoformat(timespec='seconds')}")
            run_once(collection)
            print(f"\n[WAIT] {INTERVAL_SECONDS // 60}분 후 다시 수집합니다.")
            time.sleep(INTERVAL_SECONDS)
    except KeyboardInterrupt:
        print("\n[STOP] 사용자가 프로그램을 종료했습니다.")
    except Exception as exc:
        print(f"\n[FATAL ERROR] {exc}")
    finally:
        if client:
            client.close()
            print("[MONGO] 연결 종료")


if __name__ == "__main__":
    main()
