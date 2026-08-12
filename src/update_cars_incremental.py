"""모듈화된 5분 주기 차량 증분 갱신 실행 진입점."""

import time

from pipelines.cars import run_incremental_once


# =============================================================================
# [update 코드 시작] 5분 반복 실행
# 기능: 원본 update_cars_incremental.py의 main()과 동일하게 Ctrl+C 전까지 증분 실행한다.
# =============================================================================
INTERVAL_SECONDS = 300


def main():
    print("================================")
    print(" 차량 5분 주기 최신화 시작")
    print(" 종료: Ctrl + C")
    print("================================")

    while True:
        try:
            run_incremental_once()
            print("\n[WAIT] 5분 후 다시 확인합니다.")
            time.sleep(INTERVAL_SECONDS)
        except KeyboardInterrupt:
            print("\n[STOP] 업데이트 종료")
            break


if __name__ == "__main__":
    main()
# =============================================================================
# [update 코드 끝]
# =============================================================================
