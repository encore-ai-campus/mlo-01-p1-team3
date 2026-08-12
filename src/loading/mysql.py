"""원본 MySQL 테이블 생성, Upsert, 초기·증분 실행 로그 적재."""

# =============================================================================
# [MySQL 적재 시작] 원본 테이블 생성
# 기능: business_areas, cars, crawl_logs 테이블과 차량 FK를 준비한다.
# 원본 위치: load_cars_initial.py의 create_tables()
# =============================================================================
def create_tables(conn):
    with conn.cursor() as cursor:
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS business_areas (
                business_area_code VARCHAR(100) PRIMARY KEY,
                business_area_name VARCHAR(255),
                dealer_id VARCHAR(100),
                dealer_name VARCHAR(100),
                department VARCHAR(255),
                position VARCHAR(100)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS cars (
                car_id BIGINT PRIMARY KEY,
                listing_number VARCHAR(100) NOT NULL UNIQUE,
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
                CONSTRAINT fk_car_business_area FOREIGN KEY (business_area_code)
                    REFERENCES business_areas(business_area_code)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS crawl_logs (
                log_id BIGINT AUTO_INCREMENT PRIMARY KEY,
                source_type VARCHAR(20),
                source_name VARCHAR(255),
                started_at DATETIME,
                finished_at DATETIME,
                fetched_count INT DEFAULT 0,
                inserted_count INT DEFAULT 0,
                updated_count INT DEFAULT 0,
                failed_count INT DEFAULT 0,
                status VARCHAR(30),
                error_message TEXT,
                last_seq BIGINT NULL
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """
        )
    conn.commit()
# =============================================================================
# [MySQL 적재 끝]
# =============================================================================


# =============================================================================
# [MySQL 적재 시작] business_areas·cars Upsert
# 기능: FK 부모를 먼저 저장하고, car_id 기준으로 차량을 신규/수정 처리한다.
# 원본 위치: load_cars_initial.py의 upsert_business_area(), upsert_car()
# =============================================================================
def upsert_business_area(cursor, raw):
    area = raw.get("businessArea") or {}
    dealer = raw.get("dealer") or {}
    business_area_code = area.get("id")

    if not business_area_code:
        return

    cursor.execute(
        """
        INSERT INTO business_areas (
            business_area_code, business_area_name, dealer_id,
            dealer_name, department, position
        ) VALUES (%s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            business_area_name = VALUES(business_area_name),
            dealer_id = VALUES(dealer_id),
            dealer_name = VALUES(dealer_name),
            department = VALUES(department),
            position = VALUES(position)
        """,
        (
            business_area_code,
            area.get("name"),
            dealer.get("code"),
            dealer.get("displayName"),
            dealer.get("department"),
            dealer.get("position"),
        ),
    )


def upsert_car(cursor, car):
    cursor.execute("SELECT car_id FROM cars WHERE car_id = %s", (car["car_id"],))
    exists = cursor.fetchone()

    cursor.execute(
        """
        INSERT INTO cars (
            car_id, listing_number, dealer_id, business_area_code, brand, model, trim,
            model_year, first_registration_date, mileage_km, price, currency, fuel_type,
            transmission, color, displacement_cc, status, accident_count,
            owner_change_count, inspection_status, province, city, listing_date
        ) VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
        ) ON DUPLICATE KEY UPDATE
            dealer_id = VALUES(dealer_id), business_area_code = VALUES(business_area_code),
            brand = VALUES(brand), model = VALUES(model), trim = VALUES(trim),
            model_year = VALUES(model_year), first_registration_date = VALUES(first_registration_date),
            mileage_km = VALUES(mileage_km), price = VALUES(price), currency = VALUES(currency),
            fuel_type = VALUES(fuel_type), transmission = VALUES(transmission), color = VALUES(color),
            displacement_cc = VALUES(displacement_cc), status = VALUES(status),
            accident_count = VALUES(accident_count), owner_change_count = VALUES(owner_change_count),
            inspection_status = VALUES(inspection_status), province = VALUES(province),
            city = VALUES(city), listing_date = VALUES(listing_date)
        """,
        (
            car["car_id"], car["listing_number"], car["dealer_id"], car["business_area_code"],
            car["brand"], car["model"], car["trim"], car["model_year"],
            car["first_registration_date"], car["mileage_km"], car["price"], car["currency"],
            car["fuel_type"], car["transmission"], car["color"], car["displacement_cc"],
            car["status"], car["accident_count"], car["owner_change_count"],
            car["inspection_status"], car["province"], car["city"], car["listing_date"],
        ),
    )
    return "updated" if exists else "inserted"
# =============================================================================
# [MySQL 적재 끝]
# =============================================================================


# =============================================================================
# [update 코드 시작] 마지막 checkpoint 조회와 증분 로그 저장
# 기능: 성공한 마지막 last_seq를 읽고, 증분 실행 결과를 crawl_logs에 기록한다.
# 원본 위치: update_cars_incremental.py의 get_last_seq(), write_incremental_log()
# =============================================================================
def get_last_seq(cursor):
    cursor.execute(
        """
        SELECT last_seq
        FROM crawl_logs
        WHERE source_name = 'AutoData Lab Changes'
          AND last_seq IS NOT NULL
          AND status IN ('SUCCESS', 'PARTIAL_SUCCESS')
        ORDER BY log_id DESC
        LIMIT 1
        """
    )
    row = cursor.fetchone()
    return row["last_seq"] if row else 0


def write_incremental_log(conn, started_at, finished_at, fetched, inserted, updated, failed, status, last_seq, error_message=None):
    with conn.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO crawl_logs (
                source_type, source_name, started_at, finished_at,
                fetched_count, inserted_count, updated_count, failed_count,
                status, error_message, last_seq
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                "API", "AutoData Lab Changes", started_at, finished_at,
                fetched, inserted, updated, failed, status, error_message, last_seq,
            ),
        )
    conn.commit()
# =============================================================================
# [update 코드 끝]
# =============================================================================


# =============================================================================
# [MySQL 적재 시작] 초기 적재 로그 저장
# 기능: 초기 최대 10,000건 적재 결과를 crawl_logs에 기록한다.
# 원본 위치: load_cars_initial.py의 write_log()
# =============================================================================
def write_initial_log(conn, started_at, finished_at, fetched, inserted, updated, failed, status, error_message=None):
    with conn.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO crawl_logs (
                source_type, source_name, started_at, finished_at,
                fetched_count, inserted_count, updated_count, failed_count,
                status, error_message
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                "API", "AutoData Lab Cars Initial", started_at, finished_at,
                fetched, inserted, updated, failed, status, error_message,
            ),
        )
    conn.commit()
# =============================================================================
# [MySQL 적재 끝]
# =============================================================================
