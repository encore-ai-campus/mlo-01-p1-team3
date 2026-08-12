import os
import time
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup
from pymongo import MongoClient, ASCENDING
from dotenv import load_dotenv


load_dotenv()


# =========================================================
# 기본 설정
# =========================================================

BASE_URL = "http://192.168.0.51:4000"

FAQ_URL = f"{BASE_URL}/faqs"


MONGO_URI = os.getenv(
    "MONGO_URI",
    "mongodb://localhost:27017"
)

MONGO_DATABASE = os.getenv(
    "MONGO_DATABASE",
    "car_data"
)

MONGO_COLLECTION = os.getenv(
    "MONGO_COLLECTION",
    "faqs"
)


# =========================================================
# 1. FAQ 페이지 요청
# =========================================================

def get_faq_page():

    print(f"[FETCH] {FAQ_URL}")

    response = requests.get(
        FAQ_URL,
        timeout=15
    )

    response.raise_for_status()

    return response.text


# =========================================================
# 2. FAQ HTML 파싱
# =========================================================

def crawl_faqs():

    html = get_faq_page()

    soup = BeautifulSoup(
        html,
        "html.parser"
    )

    faq_items = soup.select(
        "article.faq-item"
    )

    print(
        f"[CRAWL] FAQ 항목 "
        f"{len(faq_items)}개 발견"
    )

    raw_faqs = []

    for item in faq_items:

        # -----------------------------------------
        # article data-* 속성
        # -----------------------------------------

        faq_id = item.get(
            "data-faq-id"
        )

        source_url = item.get(
            "data-source-url"
        )

        reviewed_at = item.get(
            "data-reviewed-at"
        )

        brand_code = item.get(
            "data-brand"
        )

        category_code = item.get(
            "data-category"
        )

        # -----------------------------------------
        # 화면에 표시되는 브랜드
        # -----------------------------------------

        brand_element = item.select_one(
            '[data-field="brand"]'
        )

        brand = (
            brand_element.get_text(
                " ",
                strip=True
            )
            if brand_element
            else brand_code
        )

        # -----------------------------------------
        # 카테고리
        # -----------------------------------------

        category_element = item.select_one(
            '[data-field="category"]'
        )

        category = (
            category_element.get_text(
                " ",
                strip=True
            )
            if category_element
            else category_code
        )

        # -----------------------------------------
        # 질문
        # -----------------------------------------

        question_element = item.select_one(
            '[data-field="question"]'
        )

        question = (
            question_element.get_text(
                " ",
                strip=True
            )
            if question_element
            else None
        )

        # -----------------------------------------
        # 답변
        # -----------------------------------------

        answer_element = item.select_one(
            '[data-field="answer"]'
        )

        answer = (
            answer_element.get_text(
                " ",
                strip=True
            )
            if answer_element
            else None
        )

        # -----------------------------------------
        # 필수값 검증
        # -----------------------------------------

        if not faq_id:
            print(
                "[SKIP] faq_id 없음"
            )
            continue

        if not question:
            print(
                f"[SKIP] "
                f"{faq_id} "
                f"question 없음"
            )
            continue

        if not answer:
            print(
                f"[SKIP] "
                f"{faq_id} "
                f"answer 없음"
            )
            continue

        # -----------------------------------------
        # MongoDB 저장 형태
        # -----------------------------------------

        faq = {

            "faq_id": faq_id,

            "brand": brand,

            "brand_code": brand_code,

            "category": category,

            "question": question,

            "answer": answer,

            "source_url": source_url,

            "reviewed_at": reviewed_at,

            "crawl_url": FAQ_URL,

            "updated_at": datetime.now(
                timezone.utc
            )
        }

        raw_faqs.append(
            faq
        )

    print(
        f"[CRAWL] 정상 파싱 "
        f"{len(raw_faqs)}개"
    )

    return raw_faqs


# =========================================================
# 3. MongoDB 연결
# =========================================================

def get_mongo_collection():

    client = MongoClient(
        MONGO_URI,
        serverSelectionTimeoutMS=5000
    )

    # 연결 테스트
    client.admin.command(
        "ping"
    )

    db = client[
        MONGO_DATABASE
    ]

    collection = db[
        MONGO_COLLECTION
    ]

    print("[MONGO] 연결 완료")

    return client, collection


# =========================================================
# 4. MongoDB INDEX
# =========================================================

def create_indexes(collection):

    # FAQ 자체 고유 ID
    collection.create_index(
        [
            (
                "faq_id",
                ASCENDING
            )
        ],
        unique=True,
        name="uq_faq_id"
    )

    # 브랜드 조회용
    collection.create_index(
        [
            (
                "brand",
                ASCENDING
            )
        ],
        name="idx_brand"
    )

    # 카테고리 조회용
    collection.create_index(
        [
            (
                "category",
                ASCENDING
            )
        ],
        name="idx_category"
    )

    print(
        "[MONGO] 인덱스 확인 완료"
    )


# =========================================================
# 5. FAQ UPSERT
# =========================================================

def upsert_faq(
    collection,
    faq
):

    result = collection.update_one(

        # FAQ 고유 ID를 기준으로 식별
        {
            "faq_id": faq["faq_id"]
        },

        {
            "$set": faq,

            "$setOnInsert": {

                "created_at":
                    datetime.now(
                        timezone.utc
                    )
            }
        },

        upsert=True
    )

    if result.upserted_id:
        return "inserted"

    return "updated"


# =========================================================
# 6. MAIN
# =========================================================

def main():

    client = None

    fetched = 0
    inserted = 0
    updated = 0
    failed = 0

    try:

        print(
            "\n=========================="
        )
        print(
            " FAQ 크롤링 시작"
        )
        print(
            "==========================\n"
        )

        # -----------------------------------------
        # FAQ 크롤링
        # -----------------------------------------

        raw_faqs = crawl_faqs()

        fetched = len(
            raw_faqs
        )

        # -----------------------------------------
        # MongoDB 연결
        # -----------------------------------------

        client, collection = (
            get_mongo_collection()
        )

        create_indexes(
            collection
        )

        # -----------------------------------------
        # MongoDB 저장
        # -----------------------------------------

        for index, faq in enumerate(
            raw_faqs,
            start=1
        ):

            try:

                result = upsert_faq(
                    collection,
                    faq
                )

                if result == "inserted":

                    inserted += 1

                else:

                    updated += 1

                print(
                    f"[{index}/{fetched}] "
                    f"{faq['faq_id']} "
                    f"| {faq['brand']} "
                    f"| {result}"
                )

                # 서버 부하 방지
                time.sleep(0.05)

            except Exception as e:

                failed += 1

                print(
                    f"[ERROR] "
                    f"{faq.get('faq_id')} "
                    f"{e}"
                )

        print(
            "\n=========================="
        )
        print(
            " FAQ MongoDB 적재 완료"
        )
        print(
            "=========================="
        )

        print(
            f"수집 : {fetched}"
        )

        print(
            f"신규 : {inserted}"
        )

        print(
            f"수정 : {updated}"
        )

        print(
            f"실패 : {failed}"
        )

    except Exception as e:

        print(
            f"\n[FATAL ERROR] {e}"
        )

    finally:

        if client:

            client.close()

            print(
                "[MONGO] 연결 종료"
            )


if __name__ == "__main__":
    main()