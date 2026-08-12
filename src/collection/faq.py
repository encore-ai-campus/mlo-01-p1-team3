"""원본 FAQ 페이지 요청과 HTML 파싱."""

import requests
from bs4 import BeautifulSoup

from common.config import FAQ_URL


# =============================================================================
# [FAQ 수집 시작] FAQ 페이지 요청 및 HTML 필드 추출
# 기능: 원본 FAQ HTML에서 유효한 질문·답변 항목을 원본 MongoDB 문서 구조로 수집한다.
# 원본 위치: load_faqs_mongodb.py의 get_faq_page(), get_text_or_default(), crawl_faqs()
# =============================================================================
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

        raw_faqs.append(
            {
                "faq_id": faq_id,
                "brand": brand,
                "brand_code": brand_code,
                "category": category,
                "question": question,
                "answer": answer,
                "source_url": source_url,
                "reviewed_at": reviewed_at,
                "crawl_url": FAQ_URL,
            }
        )

    print(f"[CRAWL] 정상 파싱 {len(raw_faqs)}개")
    return raw_faqs
# =============================================================================
# [FAQ 수집 끝]
# =============================================================================
