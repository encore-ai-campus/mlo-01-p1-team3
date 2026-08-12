"""MySQL Primary 적재와 파이프라인 실행 이력 관리를 담당한다."""

from datetime import datetime
from typing import Any

import pymysql

from config import Settings
from models import LoadStats, PipelineResult, RejectedRecord
from transformers import normalize_car


# ============================================================================
# MYSQL STORE START: Primary 전용 UPSERT와 파이프라인 메타데이터를 처리한다.
# ============================================================================


def connect_mysql(settings: Settings) -> pymysql.Connection:
    """쓰기 권한이 있는 MySQL Primary에만 연결한다."""
    if not all((settings.mysql_host, settings.mysql_user, settings.mysql_database)):
        raise ValueError("MYSQL_HOST, MYSQL_USER, MYSQL_DATABASE must be configured")
    return pymysql.connect(host=settings.mysql_host, port=settings.mysql_port, user=settings.mysql_user,
                           password=settings.mysql_password, database=settings.mysql_database, charset="utf8mb4",
                           cursorclass=pymysql.cursors.DictCursor, autocommit=False)


def create_tables(conn: pymysql.Connection) -> None:
    """차량·영업소·실행이력·검증실패 테이블을 없으면 생성한다."""
    statements = [
        """CREATE TABLE IF NOT EXISTS business_areas (
            business_area_code VARCHAR(100) PRIMARY KEY, business_area_name VARCHAR(255), dealer_id VARCHAR(100),
            dealer_name VARCHAR(100), department VARCHAR(255), position VARCHAR(100)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
        """CREATE TABLE IF NOT EXISTS cars (
            car_id BIGINT PRIMARY KEY, listing_number VARCHAR(100) NOT NULL UNIQUE, dealer_id VARCHAR(100),
            business_area_code VARCHAR(100), brand VARCHAR(100), model VARCHAR(150), trim VARCHAR(150), model_year INT,
            first_registration_date DATE, mileage_km INT, price BIGINT, currency VARCHAR(20), fuel_type VARCHAR(50),
            transmission VARCHAR(50), color VARCHAR(50), displacement_cc INT, status VARCHAR(50), accident_count INT,
            owner_change_count INT, inspection_status VARCHAR(100), province VARCHAR(100), city VARCHAR(100), listing_date DATE,
            CONSTRAINT fk_car_business_area FOREIGN KEY (business_area_code) REFERENCES business_areas(business_area_code)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
        """CREATE TABLE IF NOT EXISTS etl_pipeline_runs (
            run_id BIGINT AUTO_INCREMENT PRIMARY KEY, source_name VARCHAR(50) NOT NULL, run_mode VARCHAR(30) NOT NULL,
            started_at DATETIME NOT NULL, finished_at DATETIME NULL, raw_count INT NOT NULL DEFAULT 0,
            valid_count INT NOT NULL DEFAULT 0, rejected_count INT NOT NULL DEFAULT 0, inserted_count INT NOT NULL DEFAULT 0,
            updated_count INT NOT NULL DEFAULT 0, unchanged_count INT NOT NULL DEFAULT 0, failed_count INT NOT NULL DEFAULT 0,
            last_seq BIGINT NULL, status VARCHAR(30) NOT NULL, error_message TEXT NULL,
            INDEX idx_etl_pipeline_runs_checkpoint (source_name, status, run_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
        """CREATE TABLE IF NOT EXISTS etl_rejected_records (
            rejected_id BIGINT AUTO_INCREMENT PRIMARY KEY, run_id BIGINT NULL, source_name VARCHAR(50) NOT NULL,
            reason VARCHAR(500) NOT NULL, payload JSON NOT NULL, created_at DATETIME NOT NULL,
            CONSTRAINT fk_rejected_run FOREIGN KEY (run_id) REFERENCES etl_pipeline_runs(run_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
    ]
    with conn.cursor() as cursor:
        for statement in statements:
            cursor.execute(statement)
    conn.commit()


def get_last_successful_seq(conn: pymysql.Connection) -> int:
    """성공 또는 부분 성공한 cars 증분 작업의 마지막 안전 체크포인트를 반환한다."""
    with conn.cursor() as cursor:
        cursor.execute("""SELECT last_seq FROM etl_pipeline_runs
            WHERE source_name = 'cars' AND run_mode = 'incremental' AND status IN ('SUCCESS', 'PARTIAL_SUCCESS')
              AND last_seq IS NOT NULL ORDER BY run_id DESC LIMIT 1""")
        row = cursor.fetchone()
    return int(row["last_seq"]) if row else 0


def _upsert_business_area(cursor: Any, raw: dict[str, Any]) -> None:
    """cars 외래키가 참조하는 영업소 정보를 먼저 UPSERT한다."""
    area, dealer = raw.get("businessArea") or {}, raw.get("dealer") or {}
    code = area.get("id")
    if not code:
        return
    cursor.execute("""INSERT INTO business_areas (business_area_code, business_area_name, dealer_id, dealer_name, department, position)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE business_area_name=VALUES(business_area_name), dealer_id=VALUES(dealer_id),
        dealer_name=VALUES(dealer_name), department=VALUES(department), position=VALUES(position)""",
        (code, area.get("name"), dealer.get("code"), dealer.get("displayName"), dealer.get("department"), dealer.get("position")))


CAR_COLUMNS = ("car_id", "listing_number", "dealer_id", "business_area_code", "brand", "model", "trim", "model_year",
               "first_registration_date", "mileage_km", "price", "currency", "fuel_type", "transmission", "color",
               "displacement_cc", "status", "accident_count", "owner_change_count", "inspection_status", "province", "city", "listing_date")


def _upsert_car(cursor: Any, car: dict[str, Any]) -> str:
    """car_id 기준으로 차량을 UPSERT하고 신규/수정 결과를 반환한다."""
    cursor.execute("SELECT car_id FROM cars WHERE car_id = %s", (car["car_id"],))
    exists = cursor.fetchone() is not None
    placeholders = ", ".join(["%s"] * len(CAR_COLUMNS))
    updates = ", ".join(f"{column}=VALUES({column})" for column in CAR_COLUMNS if column not in ("car_id", "listing_number"))
    cursor.execute(f"INSERT INTO cars ({', '.join(CAR_COLUMNS)}) VALUES ({placeholders}) ON DUPLICATE KEY UPDATE {updates}",
                   tuple(car[column] for column in CAR_COLUMNS))
    return "updated" if exists else "inserted"


def load_cars(conn: pymysql.Connection, raw_cars: list[dict[str, Any]]) -> LoadStats:
    """검증된 차량을 트랜잭션 단위로 MySQL Primary에 적재한다."""
    stats = LoadStats()
    try:
        with conn.cursor() as cursor:
            for raw in raw_cars:
                _upsert_business_area(cursor, raw)
                result = _upsert_car(cursor, normalize_car(raw))
                setattr(stats, result, getattr(stats, result) + 1)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return stats


def write_run(conn: pymysql.Connection, result: PipelineResult, run_mode: str, started_at: datetime, status: str) -> int:
    """한 source 실행 결과를 기록하고 생성된 run_id를 반환한다."""
    with conn.cursor() as cursor:
        cursor.execute("""INSERT INTO etl_pipeline_runs
            (source_name, run_mode, started_at, finished_at, raw_count, valid_count, rejected_count, inserted_count,
             updated_count, unchanged_count, failed_count, last_seq, status, error_message)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (result.source_name, run_mode, started_at, datetime.now(), result.raw_count, result.valid_count,
             result.rejected_count, result.load_stats.inserted, result.load_stats.updated, result.load_stats.unchanged,
             result.load_stats.failed, result.last_seq, status, result.error_message))
        run_id = cursor.lastrowid
    conn.commit()
    return int(run_id)


def write_rejected_records(conn: pymysql.Connection, run_id: int, records: list[RejectedRecord]) -> None:
    """검증 실패 데이터도 MySQL 관리 테이블에 감사 목적으로 남긴다."""
    if not records:
        return
    import json
    with conn.cursor() as cursor:
        cursor.executemany("INSERT INTO etl_rejected_records (run_id, source_name, reason, payload, created_at) VALUES (%s, %s, %s, %s, %s)",
                           [(run_id, record.source_name, record.reason, json.dumps(record.payload, ensure_ascii=False, default=str), datetime.now()) for record in records])
    conn.commit()


# ============================================================================
# MYSQL STORE END: MySQL Primary 적재·실행 이력 기능의 끝.
# ============================================================================
