import os
import time
from datetime import datetime

import pymysql
import requests
from dotenv import load_dotenv


# =========================================================
# .env 로드
# =========================================================

load_dotenv()


# =========================================================
# 기본 설정
# =========================================================

BASE_URL = "http://192.168.0.51:4000"

PUBLIC_KEY_URL = f"{BASE_URL}/api/v1/public-key"
CARS_URL = f"{BASE_URL}/api/v1/cars"

# ---------------------------------------------------------
# 초기 적재 설정
#
# 100건 × 100페이지 = 최대 10,000건
# ---------------------------------------------------------

PAGE_SIZE = 100
MAX_PAGES = 100


# =========================================================
# MySQL 설정
# =========================================================

MYSQL_CONFIG = {
    "host": os.getenv("MYSQL_HOST"),
    "port": int(os.getenv("MYSQL_PORT", 3306)),
    "user": os.getenv("MYSQL_USER"),
    "password": os.getenv("MYSQL_PASSWORD"),
    "database": os.getenv("MYSQL_DATABASE"),
    "charset": "utf8mb4",
    "cursorclass": pymysql.cursors.DictCursor,
    "autocommit": False,
}


# =========================================================
# 1. API KEY 조회
# =========================================================

def get_api_key():

    response = requests.get(
        PUBLIC_KEY_URL,
        timeout=10
    )

    response.raise_for_status()

    body = response.json()

    api_key = body["data"]["current"]["api_key"]

    print("[API KEY] 현재 API Key 조회 완료")

    return api_key


# =========================================================
# 2. API 호출
#
# 403  -> API Key 갱신
# 429  -> Rate Limit 대기 후 재시도
# Timeout / Connection Error -> 재시도
# =========================================================

def request_api(url, api_key):

    max_retries = 10
    retry_count = 0

    while True:

        try:

            headers = {
                "X-API-Key": api_key
            }

            response = requests.get(
                url,
                headers=headers,
                timeout=(10, 30)
            )

            # -------------------------------------------------
            # API Key 변경
            # -------------------------------------------------

            if response.status_code == 403:

                retry_count += 1

                if retry_count > max_retries:
                    response.raise_for_status()

                print(
                    "[WARN] API Key 변경 감지 "
                    "-> 새 Key 조회"
                )

                api_key = get_api_key()

                time.sleep(2)

                continue

            # -------------------------------------------------
            # Rate Limit
            # -------------------------------------------------

            if response.status_code == 429:

                retry_count += 1

                if retry_count > max_retries:
                    response.raise_for_status()

                retry_after = response.headers.get(
                    "Retry-After"
                )

                if retry_after:

                    try:
                        wait_seconds = int(
                            retry_after
                        )

                    except ValueError:
                        wait_seconds = 10

                else:

                    wait_seconds = min(
                        5 * retry_count,
                        60
                    )

                print(
                    f"[429] 요청 제한 발생 "
                    f"-> {wait_seconds}초 대기 "
                    f"({retry_count}/{max_retries})"
                )

                time.sleep(
                    wait_seconds
                )

                continue

            # -------------------------------------------------
            # 기타 HTTP 오류
            # -------------------------------------------------

            response.raise_for_status()

            return (
                response.json(),
                api_key
            )

        # -----------------------------------------------------
        # 네트워크 관련 오류
        # -----------------------------------------------------

        except (
            requests.exceptions.ConnectTimeout,
            requests.exceptions.ReadTimeout,
            requests.exceptions.ConnectionError
        ) as e:

            retry_count += 1

            if retry_count > max_retries:
                raise

            wait_seconds = min(
                5 * retry_count,
                60
            )

            print(
                f"[NETWORK] "
                f"{type(e).__name__} "
                f"-> {wait_seconds}초 후 재시도 "
                f"({retry_count}/{max_retries})"
            )

            time.sleep(
                wait_seconds
            )


# =========================================================
# 3. 유틸 함수
# =========================================================

def value_from(
    obj,
    *keys,
    default=None
):

    if not isinstance(obj, dict):
        return default

    for key in keys:

        value = obj.get(key)

        if value is not None:
            return value

    return default


def normalize_date(value):

    if not value:
        return None

    if isinstance(value, str):

        # 예:
        # 2026-08-11T10:20:30
        # ↓
        # 2026-08-11

        return value[:10]

    return value


# =========================================================
# 4. 차량 JSON 정규화
# =========================================================

def normalize_car(raw):

    brand = raw.get("brand") or {}
    model = raw.get("model") or {}
    dealer = raw.get("dealer") or {}
    area = raw.get("businessArea") or {}
    location = raw.get("location") or {}

    return {
        "car_id": raw.get("id"),
        "listing_number": raw.get("listingNumber"),

        "dealer_id": dealer.get("code"),
        "business_area_code": area.get("id"),

        "brand": value_from(
            brand,
            "name",
            default=brand if isinstance(brand, str) else None
        ),

        "model": value_from(
            model,
            "name",
            default=model if isinstance(model, str) else None
        ),

        "trim": raw.get("trim"),
        "model_year": raw.get("modelYear"),

        "first_registration_date": normalize_date(
            raw.get("firstRegistration")
            or raw.get("firstRegistrationDate")
            or raw.get("firstRegisteredAt")
        ),

        "mileage_km": raw.get("mileageKm"),
        "price": raw.get("price"),
        "currency": raw.get("currency"),

        "fuel_type": raw.get("fuelType") or raw.get("fuel"),
        "transmission": raw.get("transmission"),
        "color": raw.get("color"),

        "displacement_cc": (
            raw.get("displacementCc")
            or raw.get("engineDisplacementCc")
        ),

        "status": raw.get("status"),

        "accident_count": raw.get("accidentCount"),
        "owner_change_count": raw.get("ownerChangeCount"),
        "inspection_status": raw.get("inspectionStatus"),

        "province": value_from(
            location,
            "province",
            "sido",
            "region"
        ),

        "city": value_from(
            location,
            "city",
            "sigungu",
            "district"
        ),

        "listing_date": normalize_date(
            raw.get("listingDate")
            or raw.get("registeredDate")
            or raw.get("createdAt")
        )
    }


# =========================================================
# 5. MySQL 테이블 생성
#
# FAQ 테이블 없음
# =========================================================

def create_tables(conn):

    with conn.cursor() as cursor:

        # -------------------------------------------------
        # business_areas
        # -------------------------------------------------

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS business_areas (

            business_area_code VARCHAR(100)
                PRIMARY KEY,

            business_area_name VARCHAR(255),

            dealer_id VARCHAR(100),

            dealer_name VARCHAR(100),

            department VARCHAR(255),

            position VARCHAR(100)

        ) ENGINE=InnoDB
        DEFAULT CHARSET=utf8mb4;
        """)

        # -------------------------------------------------
        # cars
        # -------------------------------------------------

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS cars (

            car_id BIGINT
                PRIMARY KEY,

            listing_number VARCHAR(100)
                NOT NULL
                UNIQUE,

            dealer_id VARCHAR(100),

            business_area_code VARCHAR(100),

            brand VARCHAR(100),

            model VARCHAR(150),

            trim VARCHAR(150),

            model_year INT,

            first_registration_date DATE,

            mileage_km INT,

            price BIGINT,

            currency VARCHAR(20),

            fuel_type VARCHAR(50),

            transmission VARCHAR(50),

            color VARCHAR(50),

            displacement_cc INT,

            status VARCHAR(50),

            accident_count INT,

            owner_change_count INT,

            inspection_status VARCHAR(100),

            province VARCHAR(100),

            city VARCHAR(100),

            listing_date DATE,

            CONSTRAINT fk_car_business_area
                FOREIGN KEY (
                    business_area_code
                )
                REFERENCES business_areas(
                    business_area_code
                )

        ) ENGINE=InnoDB
        DEFAULT CHARSET=utf8mb4;
        """)

        # -------------------------------------------------
        # crawl_logs
        # -------------------------------------------------

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS crawl_logs (

            log_id BIGINT AUTO_INCREMENT
                PRIMARY KEY,

            source_type VARCHAR(20),

            source_name VARCHAR(255),

            started_at DATETIME,

            finished_at DATETIME,

            fetched_count INT DEFAULT 0,

            inserted_count INT DEFAULT 0,

            updated_count INT DEFAULT 0,

            failed_count INT DEFAULT 0,

            status VARCHAR(30),

            error_message TEXT

        ) ENGINE=InnoDB
        DEFAULT CHARSET=utf8mb4;
        """)

    conn.commit()


# =========================================================
# 6. business_areas UPSERT
# =========================================================

def upsert_business_area(
    cursor,
    raw
):

    area = (
        raw.get("businessArea")
        or {}
    )

    dealer = (
        raw.get("dealer")
        or {}
    )

    # 실제 API JSON 구조
    business_area_code = (
        area.get("id")
    )

    business_area_name = (
        area.get("name")
    )

    dealer_id = (
        dealer.get("code")
    )

    # 마스킹된 이름
    # 예: 교○○
    dealer_name = (
        dealer.get("displayName")
    )

    department = (
        dealer.get("department")
    )

    position = (
        dealer.get("position")
    )

    if not business_area_code:
        return

    sql = """
    INSERT INTO business_areas (

        business_area_code,
        business_area_name,

        dealer_id,
        dealer_name,

        department,
        position
    )

    VALUES (
        %s, %s,
        %s, %s,
        %s, %s
    )

    ON DUPLICATE KEY UPDATE

        business_area_name =
            VALUES(business_area_name),

        dealer_id =
            VALUES(dealer_id),

        dealer_name =
            VALUES(dealer_name),

        department =
            VALUES(department),

        position =
            VALUES(position)
    """

    values = (

        business_area_code,
        business_area_name,

        dealer_id,
        dealer_name,

        department,
        position
    )

    cursor.execute(
        sql,
        values
    )


# =========================================================
# 7. cars UPSERT
# =========================================================

def upsert_car(
    cursor,
    car
):

    # -----------------------------------------------------
    # 기존 차량인지 확인
    # -----------------------------------------------------

    cursor.execute(
        """
        SELECT car_id
        FROM cars
        WHERE car_id = %s
        """,
        (
            car["car_id"],
        )
    )

    exists = (
        cursor.fetchone()
    )

    # -----------------------------------------------------
    # UPSERT
    # -----------------------------------------------------

    sql = """
    INSERT INTO cars (

        car_id,
        listing_number,

        dealer_id,
        business_area_code,

        brand,
        model,
        trim,

        model_year,
        first_registration_date,

        mileage_km,
        price,
        currency,

        fuel_type,
        transmission,
        color,
        displacement_cc,

        status,

        accident_count,
        owner_change_count,
        inspection_status,

        province,
        city,

        listing_date
    )

    VALUES (

        %s, %s,

        %s, %s,

        %s, %s, %s,

        %s, %s,

        %s, %s, %s,

        %s, %s, %s, %s,

        %s,

        %s, %s, %s,

        %s, %s,

        %s
    )

    ON DUPLICATE KEY UPDATE

        dealer_id =
            VALUES(dealer_id),

        business_area_code =
            VALUES(business_area_code),

        brand =
            VALUES(brand),

        model =
            VALUES(model),

        trim =
            VALUES(trim),

        model_year =
            VALUES(model_year),

        first_registration_date =
            VALUES(first_registration_date),

        mileage_km =
            VALUES(mileage_km),

        price =
            VALUES(price),

        currency =
            VALUES(currency),

        fuel_type =
            VALUES(fuel_type),

        transmission =
            VALUES(transmission),

        color =
            VALUES(color),

        displacement_cc =
            VALUES(displacement_cc),

        status =
            VALUES(status),

        accident_count =
            VALUES(accident_count),

        owner_change_count =
            VALUES(owner_change_count),

        inspection_status =
            VALUES(inspection_status),

        province =
            VALUES(province),

        city =
            VALUES(city),

        listing_date =
            VALUES(listing_date)
    """

    values = (

        car["car_id"],
        car["listing_number"],

        car["dealer_id"],
        car["business_area_code"],

        car["brand"],
        car["model"],
        car["trim"],

        car["model_year"],
        car["first_registration_date"],

        car["mileage_km"],
        car["price"],
        car["currency"],

        car["fuel_type"],
        car["transmission"],
        car["color"],
        car["displacement_cc"],

        car["status"],

        car["accident_count"],
        car["owner_change_count"],
        car["inspection_status"],

        car["province"],
        car["city"],

        car["listing_date"]
    )

    cursor.execute(
        sql,
        values
    )

    if exists:
        return "updated"

    return "inserted"


# =========================================================
# 8. crawl_logs 저장
# =========================================================

def write_log(
    conn,
    started_at,
    finished_at,
    fetched,
    inserted,
    updated,
    failed,
    status,
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
        error_message
    )

    VALUES (

        %s, %s,

        %s, %s,

        %s, %s, %s, %s,

        %s, %s
    )
    """

    values = (

        "API",
        "AutoData Lab Cars Initial",

        started_at,
        finished_at,

        fetched,
        inserted,
        updated,
        failed,

        status,
        error_message
    )

    with conn.cursor() as cursor:

        cursor.execute(
            sql,
            values
        )

    conn.commit()


# =========================================================
# 9. 최신 10,000건 초기 적재
#
# 핵심:
#
# page 1 ~ 100
# page_size = 100
#
# 최대 10,000건
#
# 한 페이지 조회 후 바로 MySQL 적재
# =========================================================

def load_initial_cars(
    conn,
    cursor
):

    api_key = get_api_key()

    fetched = 0
    inserted = 0
    updated = 0
    failed = 0

    # 같은 실행에서 중복 API 응답 체크
    seen_car_ids = set()

    # -----------------------------------------------------
    # 1 ~ 100 페이지
    # -----------------------------------------------------

    for page in range(
        1,
        MAX_PAGES + 1
    ):

        url = (
            f"{CARS_URL}"
            f"?sort=newest"
            f"&page={page}"
            f"&page_size={PAGE_SIZE}"
        )

        print(
            f"\n[FETCH] "
            f"page={page}/{MAX_PAGES}"
        )

        result, api_key = request_api(
            url,
            api_key
        )

        data = result.get(
            "data",
            []
        )

        if not data:

            print(
                "[FETCH] 데이터 없음 -> 종료"
            )

            break

        fetched += len(data)

        # -------------------------------------------------
        # 해당 페이지 데이터 즉시 MySQL 저장
        # -------------------------------------------------

        for raw in data:

            car_id = raw.get("id")

            # ---------------------------------------------
            # API 중복 응답 확인
            # ---------------------------------------------

            if car_id in seen_car_ids:

                print(
                    f"[WARN] "
                    f"중복 car_id={car_id}"
                )

            else:

                seen_car_ids.add(
                    car_id
                )

            try:

                # -----------------------------------------
                # business_area 먼저
                #
                # cars가 FK로 참조하기 때문
                # -----------------------------------------

                upsert_business_area(
                    cursor,
                    raw
                )

                # -----------------------------------------
                # 차량 정규화
                # -----------------------------------------
             
                car = normalize_car(
                    raw
                )

                # -----------------------------------------
                # 차량 저장
                # -----------------------------------------

                result_type = upsert_car(
                    cursor,
                    car
                )

                if result_type == "inserted":

                    inserted += 1

                else:

                    updated += 1

            except Exception as e:

                failed += 1

                print(
                    f"[ERROR] "
                    f"car_id={car_id} "
                    f"{e}"
                )

        # -------------------------------------------------
        # 페이지 100건 단위 COMMIT
        # -------------------------------------------------

        conn.commit()

        print(
            f"[LOAD] "
            f"{page}/{MAX_PAGES}"
            f" | API누적={fetched}"
            f" | 고유차량={len(seen_car_ids)}"
            f" | 신규={inserted}"
            f" | 수정={updated}"
            f" | 실패={failed}"
        )

        # -------------------------------------------------
        # Rate Limit 방지
        # -------------------------------------------------

        time.sleep(1.0)

    return (
        fetched,
        inserted,
        updated,
        failed,
        len(seen_car_ids)
    )


# =========================================================
# 10. MAIN
# =========================================================

def main():

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

        print(
            "[MYSQL] 연결 완료"
        )

        # -------------------------------------------------
        # 테이블 확인/생성
        # -------------------------------------------------

        create_tables(
            conn
        )

        cursor = conn.cursor()

        print(
            "\n================================="
        )
        print(
            " 최신 차량 10,000건 초기 적재 시작"
        )
        print(
            "=================================\n"
        )

        # -------------------------------------------------
        # 초기 적재
        # -------------------------------------------------

        (
            fetched,
            inserted,
            updated,
            failed,
            unique_count
        ) = load_initial_cars(
            conn,
            cursor
        )

        finished_at = (
            datetime.now()
        )

        status = (
            "SUCCESS"
            if failed == 0
            else "PARTIAL_SUCCESS"
        )

        # -------------------------------------------------
        # 로그
        # -------------------------------------------------

        write_log(
            conn,
            started_at,
            finished_at,
            fetched,
            inserted,
            updated,
            failed,
            status
        )

        # -------------------------------------------------
        # 결과
        # -------------------------------------------------

        print(
            "\n================================="
        )
        print(
            " 초기 차량 적재 완료"
        )
        print(
            "================================="
        )

        print(
            f"API 조회      : {fetched}"
        )

        print(
            f"고유 car_id    : {unique_count}"
        )

        print(
            f"신규 INSERT   : {inserted}"
        )

        print(
            f"기존 UPDATE   : {updated}"
        )

        print(
            f"실패          : {failed}"
        )

        print(
            f"상태          : {status}"
        )

        # -------------------------------------------------
        # 간단한 검증
        # -------------------------------------------------

        cursor.execute(
            """
            SELECT COUNT(*) AS cnt
            FROM cars
            """
        )

        total_cars = (
            cursor.fetchone()["cnt"]
        )

        print(
            f"MySQL cars 총 건수 : {total_cars}"
        )

        if unique_count != 10000:

            print(
                "\n[WARN] "
                "이번 API 호출에서 "
                "고유 car_id가 10,000건이 아닙니다."
            )

    # =====================================================
    # 전체 오류
    # =====================================================

    except Exception as e:

        finished_at = (
            datetime.now()
        )

        print(
            f"\n[FATAL ERROR] {e}"
        )

        if conn:

            try:

                write_log(
                    conn,
                    started_at,
                    finished_at,
                    fetched,
                    inserted,
                    updated,
                    failed + 1,
                    "FAILED",
                    str(e)
                )

            except Exception:
                pass

    # =====================================================
    # 연결 종료
    # =====================================================

    finally:

        if cursor:
            cursor.close()

        if conn:
            conn.close()

        print(
            "[MYSQL] 연결 종료"
        )


# =========================================================
# 실행
# =========================================================

if __name__ == "__main__":
    main()