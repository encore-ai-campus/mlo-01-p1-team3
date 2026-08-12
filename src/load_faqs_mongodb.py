"""모듈화된 5분 주기 FAQ MongoDB 적재 실행 진입점."""

import time
from datetime import datetime

from loading.mongo import create_indexes, get_mongo_collection
from pipelines.faq import run_once


# =============================================================================
# [실행 진입점 시작] FAQ 5분 반복 실행
# 기능: 원본 load_faqs_mongodb.py의 main()과 동일하게 연결·인덱스 확인 후 반복 실행한다.
# =============================================================================
INTERVAL_SECONDS = 300


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
    except Exception as error:
        print(f"\n[FATAL ERROR] {error}")
    finally:
        if client:
            client.close()
            print("[MONGO] 연결 종료")


if __name__ == "__main__":
    main()
# =============================================================================
# [실행 진입점 끝]
# =============================================================================
