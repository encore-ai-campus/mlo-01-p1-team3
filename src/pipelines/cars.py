"""원본 초기 차량 적재와 증분 차량 갱신을 단계별 모듈로 조합한다."""

import time
from datetime import datetime

import pymysql

from collection.cars import get_api_key, request_api
from common.config import CARS_URL, CHANGES_URL, MYSQL_CONFIG
from loading.mysql import (
    create_tables,
    get_last_seq,
    upsert_business_area,
    upsert_car,
    write_incremental_log,
    write_initial_log,
)
from preprocessing.cars import normalize_car


# =============================================================================
# [초기 적재 파이프라인 시작] 최신 차량 페이지 수집·적재
# 기능: 원본의 page 1~100, 100건씩 최대 10,000건을 MySQL에 적재한다.
# 원본 위치: load_cars_initial.py의 load_initial_cars()
# =============================================================================
def load_initial_cars(conn, cursor):
    page_size = 100
    max_pages = 100
    api_key = get_api_key()

    fetched = 0
    inserted = 0
    updated = 0
    failed = 0
    seen_car_ids = set()

    for page in range(1, max_pages + 1):
        url = f"{CARS_URL}?sort=newest&page={page}&page_size={page_size}"
        print(f"\n[FETCH] page={page}/{max_pages}")

        result, api_key = request_api(url, api_key)
        data = result.get("data", [])
        if not data:
            print("[FETCH] 데이터 없음 -> 종료")
            break

        fetched += len(data)

        for raw in data:
            car_id = raw.get("id")
            if car_id in seen_car_ids:
                print(f"[WARN] 중복 car_id={car_id}")
            else:
                seen_car_ids.add(car_id)

            try:
                upsert_business_area(cursor, raw)
                car = normalize_car(raw)
                result_type = upsert_car(cursor, car)

                if result_type == "inserted":
                    inserted += 1
                else:
                    updated += 1
            except Exception as error:
                failed += 1
                print(f"[ERROR] car_id={car_id} {error}")

        conn.commit()
        print(
            f"[LOAD] {page}/{max_pages} | API누적={fetched} | 고유차량={len(seen_car_ids)}"
            f" | 신규={inserted} | 수정={updated} | 실패={failed}"
        )
        time.sleep(1.0)

    return fetched, inserted, updated, failed, len(seen_car_ids)
# =============================================================================
# [초기 적재 파이프라인 끝]
# =============================================================================


# =============================================================================
# [초기 적재 파이프라인 시작] 초기 적재 실행·로그·검증
# 기능: MySQL 연결부터 최종 cars 총 건수 검증까지 원본 main()의 1회 실행을 수행한다.
# 원본 위치: load_cars_initial.py의 main()
# =============================================================================
def run_initial_once():
    started_at = datetime.now()
    conn = None
    cursor = None
    fetched = inserted = updated = failed = 0

    try:
        conn = pymysql.connect(**MYSQL_CONFIG)
        print("[MYSQL] 연결 완료")
        create_tables(conn)
        cursor = conn.cursor()

        print("\n=================================")
        print(" 최신 차량 10,000건 초기 적재 시작")
        print("=================================\n")

        fetched, inserted, updated, failed, unique_count = load_initial_cars(conn, cursor)
        finished_at = datetime.now()
        status = "SUCCESS" if failed == 0 else "PARTIAL_SUCCESS"
        write_initial_log(conn, started_at, finished_at, fetched, inserted, updated, failed, status)

        print("\n=================================")
        print(" 초기 차량 적재 완료")
        print("=================================")
        print(f"API 조회      : {fetched}")
        print(f"고유 car_id    : {unique_count}")
        print(f"신규 INSERT   : {inserted}")
        print(f"기존 UPDATE   : {updated}")
        print(f"실패          : {failed}")
        print(f"상태          : {status}")

        cursor.execute("SELECT COUNT(*) AS cnt FROM cars")
        total_cars = cursor.fetchone()["cnt"]
        print(f"MySQL cars 총 건수 : {total_cars}")
        if unique_count != 10000:
            print("\n[WARN] 이번 API 호출에서 고유 car_id가 10,000건이 아닙니다.")

        return {"fetched": fetched, "inserted": inserted, "updated": updated, "failed": failed, "unique_count": unique_count}

    except Exception as error:
        finished_at = datetime.now()
        print(f"\n[FATAL ERROR] {error}")
        if conn:
            try:
                write_initial_log(conn, started_at, finished_at, fetched, inserted, updated, failed + 1, "FAILED", str(error))
            except Exception:
                pass
        raise
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
        print("[MYSQL] 연결 종료")
# =============================================================================
# [초기 적재 파이프라인 끝]
# =============================================================================


# =============================================================================
# [update 코드 시작] 증분 변경분 1회 수집·적재·checkpoint 기록
# 기능: 마지막 last_seq 이후 changes를 끝까지 처리하고, 성공 이벤트마다 commit한다.
# 원본 위치: update_cars_incremental.py의 run_incremental_once()
# =============================================================================
def run_incremental_once():
    started_at = datetime.now()
    conn = None
    cursor = None
    fetched = inserted = updated = failed = 0

    try:
        conn = pymysql.connect(**MYSQL_CONFIG)
        cursor = conn.cursor()
        create_tables(conn)

        last_seq = get_last_seq(cursor)
        current_seq = last_seq

        print("\n================================")
        print(" 차량 증분 업데이트 시작")
        print("================================")
        print(f"[CHECKPOINT] last_seq={last_seq}")

        api_key = get_api_key()
        while True:
            url = f"{CHANGES_URL}?after_seq={current_seq}&limit=100"
            print(f"[CHANGES] after_seq={current_seq}")
            result, api_key = request_api(url, api_key)
            changes = result.get("data", [])

            if not changes:
                print("[CHANGES] 신규/변경 차량 없음")
                break

            print(f"[CHANGES] {len(changes)}개 이벤트 발견")
            for change in changes:
                seq = change.get("seq")
                operation = change.get("operation")
                listing_id = change.get("listingId")
                payload = change.get("payload")

                if seq is None:
                    failed += 1
                    print("[WARN] seq 없음")
                    continue
                if not payload:
                    failed += 1
                    print(f"[WARN] seq={seq} payload 없음")
                    continue

                try:
                    fetched += 1
                    upsert_business_area(cursor, payload)
                    car = normalize_car(payload)
                    result_type = upsert_car(cursor, car)

                    if result_type == "inserted":
                        inserted += 1
                    else:
                        updated += 1

                    current_seq = seq
                    conn.commit()
                    print(f"[UPSERT] seq={seq} operation={operation} car_id={listing_id} result={result_type} status={car['status']}")
                except Exception as error:
                    conn.rollback()
                    failed += 1
                    print(f"[ERROR] seq={seq} car_id={listing_id} {error}")
                    raise

            has_more = result.get("meta", {}).get("has_more", False)
            if not has_more:
                break
            time.sleep(1)

        finished_at = datetime.now()
        status = "SUCCESS" if failed == 0 else "PARTIAL_SUCCESS"
        write_incremental_log(conn, started_at, finished_at, fetched, inserted, updated, failed, status, current_seq)

        print("\n================================")
        print(" 차량 증분 업데이트 완료")
        print("================================")
        print(f"변경 이벤트 : {fetched}")
        print(f"신규 차량   : {inserted}")
        print(f"수정 차량   : {updated}")
        print(f"실패        : {failed}")
        print(f"last_seq    : {current_seq}")
        return {"fetched": fetched, "inserted": inserted, "updated": updated, "failed": failed, "last_seq": current_seq}

    except Exception as error:
        finished_at = datetime.now()
        print(f"\n[FATAL ERROR] {error}")
        if conn:
            try:
                write_incremental_log(conn, started_at, finished_at, fetched, inserted, updated, failed + 1, "FAILED", locals().get("current_seq", 0), str(error))
            except Exception:
                pass
        raise
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
# =============================================================================
# [update 코드 끝]
# =============================================================================
