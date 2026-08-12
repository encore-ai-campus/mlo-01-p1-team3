"""모듈화된 초기 적재·증분 적재·FAQ 적재 통합 실행 파일.

실행 예시
---------
python run_data_pipelines.py initial
python run_data_pipelines.py incremental --once
python run_data_pipelines.py faq --once
"""

import argparse
import time

from loading.mongo import create_indexes, get_mongo_collection
from pipelines.cars import run_incremental_once, run_initial_once
from pipelines.faq import run_once as run_faq_once


DEFAULT_INTERVAL_SECONDS = 300


# =============================================================================
# [통합 실행 시작] 초기 차량 데이터 MySQL 적재
# 기능: 최신 차량 최대 10,000건을 수집하여 MySQL에 최초 적재한다.
# 호출 모듈: pipelines.cars.run_initial_once()
# =============================================================================
def run_initial() -> None:
    run_initial_once()
# =============================================================================
# [통합 실행 끝]
# =============================================================================


# =============================================================================
# [통합 실행 시작] 차량 증분 MySQL 적재
# 기능: crawl_logs의 마지막 last_seq 이후 변경분을 5분 간격으로 적재한다.
# 호출 모듈: pipelines.cars.run_incremental_once()
# =============================================================================
def run_incremental(*, once: bool, interval_seconds: int) -> None:
    print("================================")
    print(" 차량 5분 주기 최신화 시작")
    print(" 종료: Ctrl + C")
    print("================================")

    while True:
        run_incremental_once()
        if once:
            return

        print(f"\n[WAIT] {interval_seconds // 60}분 후 다시 확인합니다.")
        time.sleep(interval_seconds)
# =============================================================================
# [통합 실행 끝]
# =============================================================================


# =============================================================================
# [통합 실행 시작] FAQ MongoDB 적재
# 기능: FAQ HTML을 수집하고 faq_id 기준으로 MongoDB에 5분 간격 Upsert한다.
# 호출 모듈: pipelines.faq.run_once()
# =============================================================================
def run_faq(*, once: bool, interval_seconds: int) -> None:
    client = None
    try:
        print("\n==========================")
        print("FAQ 5분 주기 최신화 시작")
        print("종료하려면 Ctrl+C를 누르세요.")
        print("==========================")

        client, collection = get_mongo_collection()
        create_indexes(collection)

        while True:
            run_faq_once(collection)
            if once:
                return

            print(f"\n[WAIT] {interval_seconds // 60}분 후 다시 수집합니다.")
            time.sleep(interval_seconds)
    finally:
        if client:
            client.close()
            print("[MONGO] 연결 종료")
# =============================================================================
# [통합 실행 끝]
# =============================================================================


def main() -> None:
    parser = argparse.ArgumentParser(description="모듈화된 데이터 적재 실행기")
    parser.add_argument("pipeline", choices=("initial", "incremental", "faq"), help="실행할 적재 파이프라인")
    parser.add_argument("--once", action="store_true", help="incremental 또는 faq를 한 번만 실행")
    parser.add_argument("--interval-seconds", type=int, default=DEFAULT_INTERVAL_SECONDS, help="반복 실행 간격(초), 기본값: 300")
    args = parser.parse_args()

    if args.interval_seconds <= 0:
        parser.error("--interval-seconds는 0보다 커야 합니다.")

    try:
        if args.pipeline == "initial":
            run_initial()
        elif args.pipeline == "incremental":
            run_incremental(once=args.once, interval_seconds=args.interval_seconds)
        else:
            run_faq(once=args.once, interval_seconds=args.interval_seconds)
    except KeyboardInterrupt:
        print("\n[STOP] 사용자가 프로그램을 종료했습니다.")


if __name__ == "__main__":
    main()
