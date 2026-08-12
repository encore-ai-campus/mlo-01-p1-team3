import time
from datetime import datetime

import pymysql

from load_cars_initial import (
    BASE_URL,
    MYSQL_CONFIG,
    get_api_key,
    request_api,
    normalize_car,
    upsert_business_area,
    upsert_car,
)


# =========================================================
# 설정
# =========================================================

CHANGES_URL = f"{BASE_URL}/api/v1/changes"

CHANGE_LIMIT = 100

# 5분
INTERVAL_SECONDS = 300


# =========================================================
# 마지막 checkpoint 조회
# =========================================================

def get_last_seq(cursor):

    cursor.execute("""
        SELECT last_seq
        FROM crawl_logs
        WHERE source_name = 'AutoData Lab Changes'
          AND last_seq IS NOT NULL
          AND status IN (
              'SUCCESS',
              'PARTIAL_SUCCESS'
          )
        ORDER BY log_id DESC
        LIMIT 1
    """)

    row = cursor.fetchone()

    if row:
        return row["last_seq"]

    return 0


# =========================================================
# 증분 적재 로그 저장
# =========================================================

def write_incremental_log(
    conn,
    started_at,
    finished_at,
    fetched,
    inserted,
    updated,
    failed,
    status,
    last_seq,
    error_message=None
):

    sql = """
    INSERT INTO crawl_logs (

        source_type,
        source_name,

        started_at,
        finished_at,

        fetched_count,
        inserted_count,
        updated_count,
        failed_count,

        status,
        error_message,

        last_seq
    )

    VALUES (

        %s, %s,

        %s, %s,

        %s, %s, %s, %s,

        %s, %s,

        %s
    )
    """

    values = (

        "API",
        "AutoData Lab Changes",

        started_at,
        finished_at,

        fetched,
        inserted,
        updated,
        failed,

        status,
        error_message,

        last_seq
    )

    with conn.cursor() as cursor:

        cursor.execute(
            sql,
            values
        )

    conn.commit()


# =========================================================
# 변경분 1회 수집
# =========================================================

def run_incremental_once():

    started_at = datetime.now()

    conn = None
    cursor = None

    fetched = 0
    inserted = 0
    updated = 0
    failed = 0

    try:

        # -------------------------------------------------
        # MySQL 연결
        # -------------------------------------------------

        conn = pymysql.connect(
            **MYSQL_CONFIG
        )

        cursor = conn.cursor()

        # -------------------------------------------------
        # 마지막 checkpoint
        # -------------------------------------------------

        last_seq = get_last_seq(
            cursor
        )

        current_seq = last_seq

        print("\n================================")
        print(" 차량 증분 업데이트 시작")
        print("================================")

        print(
            f"[CHECKPOINT] "
            f"last_seq={last_seq}"
        )

        # -------------------------------------------------
        # API KEY
        # -------------------------------------------------

        api_key = get_api_key()

        # -------------------------------------------------
        # changes 끝까지 처리
        # -------------------------------------------------

        while True:

            url = (
                f"{CHANGES_URL}"
                f"?after_seq={current_seq}"
                f"&limit={CHANGE_LIMIT}"
            )

            print(
                f"[CHANGES] "
                f"after_seq={current_seq}"
            )

            result, api_key = request_api(
                url,
                api_key
            )

            changes = result.get(
                "data",
                []
            )

            # ---------------------------------------------
            # 변경사항 없음
            # ---------------------------------------------

            if not changes:

                print(
                    "[CHANGES] "
                    "신규/변경 차량 없음"
                )

                break

            print(
                f"[CHANGES] "
                f"{len(changes)}개 이벤트 발견"
            )

            # ---------------------------------------------
            # 변경 이벤트 처리
            # ---------------------------------------------

            for change in changes:

                seq = change.get(
                    "seq"
                )

                operation = change.get(
                    "operation"
                )

                listing_id = change.get(
                    "listingId"
                )

                payload = change.get(
                    "payload"
                )

                # -----------------------------------------
                # 필수값 확인
                # -----------------------------------------

                if seq is None:

                    failed += 1

                    print(
                        "[WARN] seq 없음"
                    )

                    continue

                if not payload:

                    failed += 1

                    print(
                        f"[WARN] "
                        f"seq={seq} "
                        f"payload 없음"
                    )

                    continue

                try:

                    fetched += 1

                    # -------------------------------------
                    # business_areas UPSERT
                    # -------------------------------------

                    upsert_business_area(
                        cursor,
                        payload
                    )

                    # -------------------------------------
                    # payload 자체가 차량 최신 데이터
                    # -------------------------------------

                    car = normalize_car(
                        payload
                    )

                    # -------------------------------------
                    # cars UPSERT
                    # -------------------------------------

                    result_type = upsert_car(
                        cursor,
                        car
                    )

                    if result_type == "inserted":

                        inserted += 1

                    else:

                        updated += 1

                    # -------------------------------------
                    # 성공한 seq까지 checkpoint 이동
                    # -------------------------------------

                    current_seq = seq

                    conn.commit()

                    print(
                        f"[UPSERT] "
                        f"seq={seq} "
                        f"operation={operation} "
                        f"car_id={listing_id} "
                        f"result={result_type} "
                        f"status={car['status']}"
                    )

                except Exception as e:

                    conn.rollback()

                    failed += 1

                    print(
                        f"[ERROR] "
                        f"seq={seq} "
                        f"car_id={listing_id} "
                        f"{e}"
                    )

                    # 중요한 이벤트를 실패했으므로
                    # 다음 seq로 넘어가지 않음
                    raise

            # ---------------------------------------------
            # meta 확인
            # ---------------------------------------------

            meta = result.get(
                "meta",
                {}
            )

            has_more = meta.get(
                "has_more",
                False
            )

            if not has_more:

                break

            # 서버 과부하 방지
            time.sleep(1)

        # -------------------------------------------------
        # 성공 로그
        # -------------------------------------------------

        finished_at = datetime.now()

        status = (
            "SUCCESS"
            if failed == 0
            else "PARTIAL_SUCCESS"
        )

        write_incremental_log(
            conn,
            started_at,
            finished_at,

            fetched,
            inserted,
            updated,
            failed,

            status,

            current_seq
        )

        print("\n================================")
        print(" 차량 증분 업데이트 완료")
        print("================================")

        print(
            f"변경 이벤트 : {fetched}"
        )

        print(
            f"신규 차량   : {inserted}"
        )

        print(
            f"수정 차량   : {updated}"
        )

        print(
            f"실패        : {failed}"
        )

        print(
            f"last_seq    : {current_seq}"
        )

    except Exception as e:

        finished_at = datetime.now()

        print(
            f"\n[FATAL ERROR] {e}"
        )

        if conn:

            try:

                write_incremental_log(
                    conn,
                    started_at,
                    finished_at,

                    fetched,
                    inserted,
                    updated,
                    failed + 1,

                    "FAILED",

                    locals().get(
                        "current_seq",
                        0
                    ),

                    str(e)
                )

            except Exception:
                pass

    finally:

        if cursor:
            cursor.close()

        if conn:
            conn.close()


# =========================================================
# 5분 반복
# =========================================================

def main():

    print(
        "================================"
    )

    print(
        " 차량 5분 주기 최신화 시작"
    )

    print(
        " 종료: Ctrl + C"
    )

    print(
        "================================"
    )

    while True:

        try:

            run_incremental_once()

            print(
                "\n[WAIT] "
                "5분 후 다시 확인합니다."
            )

            time.sleep(
                INTERVAL_SECONDS
            )

        except KeyboardInterrupt:

            print(
                "\n[STOP] "
                "업데이트 종료"
            )

            break


if __name__ == "__main__":
    main()