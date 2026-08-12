"""Monitoring EC2에서 실행 이력과 DB 복제 상태를 읽기 전용으로 점검한다."""

import json
import logging
import sys
from typing import Any

import pymysql

from config import Settings, load_settings
from mongo_store import connect_mongodb
from mysql_store import connect_mysql


# ============================================================================
# MONITOR START: Pipeline, MySQL Replica, MongoDB Replica Set 상태를 점검한다.
# ============================================================================


def check_pipeline(conn: pymysql.Connection) -> dict[str, Any]:
    """각 source의 마지막 실행 결과가 실패인지 확인한다."""
    with conn.cursor() as cursor:
        cursor.execute("""SELECT source_name, status, raw_count, valid_count, rejected_count, failed_count, finished_at
            FROM etl_pipeline_runs WHERE run_id IN (SELECT MAX(run_id) FROM etl_pipeline_runs GROUP BY source_name)""")
        rows = cursor.fetchall()
    healthy = bool(rows) and all(row["status"] != "FAILED" for row in rows)
    return {"healthy": healthy, "runs": rows}


def check_mysql_replica(settings: Settings) -> dict[str, Any]:
    """Replica B에서 I/O·SQL thread와 replication lag를 확인한다."""
    if not settings.mysql_replica_host:
        return {"healthy": False, "error": "MYSQL_REPLICA_HOST is not configured"}
    conn = pymysql.connect(host=settings.mysql_replica_host, port=settings.mysql_replica_port,
                           user=settings.mysql_monitor_user, password=settings.mysql_monitor_password,
                           database=settings.mysql_database, charset="utf8mb4",
                           cursorclass=pymysql.cursors.DictCursor, connect_timeout=5)
    try:
        with conn.cursor() as cursor:
            cursor.execute("SHOW REPLICA STATUS")
            row = cursor.fetchone()
        if not row:
            return {"healthy": False, "error": "replication is not configured"}
        io_running = row.get("Replica_IO_Running", row.get("Slave_IO_Running"))
        sql_running = row.get("Replica_SQL_Running", row.get("Slave_SQL_Running"))
        lag = row.get("Seconds_Behind_Source", row.get("Seconds_Behind_Master"))
        return {"healthy": io_running == "Yes" and sql_running == "Yes", "io_running": io_running,
                "sql_running": sql_running, "lag_seconds": lag, "last_io_error": row.get("Last_IO_Error"),
                "last_sql_error": row.get("Last_SQL_Error")}
    finally:
        conn.close()


def check_mongodb_replica(settings: Settings) -> dict[str, Any]:
    """Replica Set 전체 URI로 상태를 읽어 PRIMARY 1개와 SECONDARY 존재 여부를 확인한다."""
    client = connect_mongodb(settings)
    try:
        status = client.admin.command("replSetGetStatus")
        members = [{"name": member.get("name"), "state": member.get("stateStr"), "health": member.get("health")} for member in status.get("members", [])]
        primary_count = sum(member["state"] == "PRIMARY" and member["health"] == 1 for member in members)
        secondary_count = sum(member["state"] == "SECONDARY" and member["health"] == 1 for member in members)
        return {"healthy": primary_count == 1 and secondary_count >= 1, "members": members}
    finally:
        client.close()


def main() -> int:
    """세 상태 점검 결과를 JSON으로 출력하고 하나라도 비정상이면 1을 반환한다."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    settings = load_settings()
    checks: dict[str, dict[str, Any]] = {}
    try:
        primary_conn = connect_mysql(settings)
        try:
            checks["pipeline"] = check_pipeline(primary_conn)
        finally:
            primary_conn.close()
    except Exception as exc:
        checks["pipeline"] = {"healthy": False, "error": str(exc)}
    try:
        checks["mysql_replica"] = check_mysql_replica(settings)
    except Exception as exc:
        checks["mysql_replica"] = {"healthy": False, "error": str(exc)}
    try:
        checks["mongodb_replica_set"] = check_mongodb_replica(settings)
    except Exception as exc:
        checks["mongodb_replica_set"] = {"healthy": False, "error": str(exc)}
    print(json.dumps(checks, ensure_ascii=False, default=str, indent=2))
    return 0 if all(check["healthy"] for check in checks.values()) else 1


if __name__ == "__main__":
    sys.exit(main())


# ============================================================================
# MONITOR END: Monitoring EC2 점검 기능의 끝.
# ============================================================================
