"""원본 FAQ 수집·MongoDB 적재 실행 흐름."""

import time

from collection.faq import crawl_faqs
from loading.mongo import upsert_faq


# =============================================================================
# [FAQ 파이프라인 시작] FAQ 단발 수집 및 MongoDB 적재
# 기능: 수집 건수, 신규·수정·변경없음·실패를 집계하고 항목별 결과를 출력한다.
# 원본 위치: load_faqs_mongodb.py의 run_once()
# =============================================================================
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
            except Exception as error:
                failed += 1
                print(f"[ERROR] {faq.get('faq_id')} {error}")
    except Exception as error:
        failed += 1
        print(f"[FATAL ERROR] {error}")

    print("\n==========================")
    print("FAQ MongoDB 반영 결과")
    print("==========================")
    print(f"수집: {fetched}")
    print(f"신규: {inserted}")
    print(f"실제수정: {updated}")
    print(f"변경없음: {unchanged}")
    print(f"실패: {failed}")
# =============================================================================
# [FAQ 파이프라인 끝]
# =============================================================================
