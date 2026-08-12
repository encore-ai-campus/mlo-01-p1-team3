"""cron이 호출하는 Collector/ETL 파이프라인의 단일 실행 진입점이다."""

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from collectors import collect_car_changes, collect_faqs, collect_initial_cars, load_local_json
from config import Settings, load_settings
from file_storage import save_raw, save_rejected
from models import PipelineResult
from mongo_store import connect_mongodb, load_faqs
from mysql_store import connect_mysql, create_tables, get_last_successful_seq, load_cars, write_rejected_records, write_run
from validators import validate_cars, validate_faqs


# ============================================================================
# MAIN START: CLI, 실행 로그, source별 ETL 오케스트레이션을 제공한다.
# ============================================================================


def configure_logging(settings: Settings) -> None:
    """cron 환경에서도 남도록 콘솔과 파일에 동일한 실행 로그를 남긴다."""
    settings.log_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                        handlers=[logging.StreamHandler(), logging.FileHandler(settings.log_dir / "pipeline.log", encoding="utf-8")])


def _event_checkpoint(records: list[dict[str, Any]]) -> int | None:
    """정상 처리 또는 rejected 처리까지 끝낸 증분 이벤트의 마지막 seq를 계산한다."""
    if not records:
        return None
    sequences = [record.get("seq") for record in records]
    if not all(isinstance(seq, int) for seq in sequences):
        raise ValueError("incremental changes response contains an event without integer seq")
    return max(sequences)


def run_cars(settings: Settings, conn: Any, mode: str, local_input: Path | None) -> PipelineResult:
    """차량 데이터를 수집·raw 보관·검증·MySQL Primary UPSERT 순서로 실행한다."""
    started_at = datetime.now()
    result = PipelineResult(source_name="cars")
    rejected = []
    try:
        if local_input:
            raw_records = load_local_json(local_input)
        elif mode == "initial":
            raw_records = collect_initial_cars(settings)
        else:
            raw_records = collect_car_changes(settings, get_last_successful_seq(conn))
        result.raw_count = len(raw_records)
        save_raw(settings, "cars", raw_records)
        valid, rejected = validate_cars(raw_records)
        result.valid_count, result.rejected_count = len(valid), len(rejected)
        result.load_stats = load_cars(conn, valid)
        if mode == "incremental" and not local_input:
            result.last_seq = _event_checkpoint(raw_records)
        status = "SUCCESS" if result.rejected_count == 0 else "PARTIAL_SUCCESS"
    except Exception as exc:
        logging.exception("cars pipeline failed")
        result.error_message = str(exc)
        result.load_stats.failed += 1
        status = "FAILED"
    save_rejected(settings, "cars", rejected)
    try:
        run_id = write_run(conn, result, mode, started_at, status)
        write_rejected_records(conn, run_id, rejected)
    except Exception:
        logging.exception("cars run history could not be recorded")
        if status != "FAILED":
            result.error_message = "run history write failed"
            result.load_stats.failed += 1
    logging.info("cars finished: status=%s raw=%s valid=%s rejected=%s inserted=%s updated=%s", status, result.raw_count, result.valid_count, result.rejected_count, result.load_stats.inserted, result.load_stats.updated)
    return result


def run_faqs(settings: Settings, conn: Any, mode: str, local_input: Path | None) -> PipelineResult:
    """FAQ 데이터를 수집·raw 보관·검증·MongoDB Replica Set UPSERT 순서로 실행한다."""
    started_at = datetime.now()
    result = PipelineResult(source_name="faqs")
    rejected = []
    client = None
    try:
        raw_records = load_local_json(local_input) if local_input else collect_faqs(settings)
        result.raw_count = len(raw_records)
        save_raw(settings, "faqs", raw_records)
        valid, rejected = validate_faqs(raw_records)
        result.valid_count, result.rejected_count = len(valid), len(rejected)
        client = connect_mongodb(settings)
        result.load_stats = load_faqs(client, settings, valid)
        status = "SUCCESS" if result.rejected_count == 0 else "PARTIAL_SUCCESS"
    except Exception as exc:
        logging.exception("FAQ pipeline failed")
        result.error_message = str(exc)
        result.load_stats.failed += 1
        status = "FAILED"
    finally:
        if client:
            client.close()
    save_rejected(settings, "faqs", rejected)
    try:
        run_id = write_run(conn, result, mode, started_at, status)
        write_rejected_records(conn, run_id, rejected)
    except Exception:
        logging.exception("FAQ run history could not be recorded")
        if status != "FAILED":
            result.error_message = "run history write failed"
            result.load_stats.failed += 1
    logging.info("FAQ finished: status=%s raw=%s valid=%s rejected=%s inserted=%s updated=%s unchanged=%s", status, result.raw_count, result.valid_count, result.rejected_count, result.load_stats.inserted, result.load_stats.updated, result.load_stats.unchanged)
    return result


def parse_arguments() -> argparse.Namespace:
    """cron과 수동 실행에서 사용할 run 명령의 옵션을 파싱한다."""
    parser = argparse.ArgumentParser(description="Collector/ETL pipeline")
    subparsers = parser.add_subparsers(dest="command", required=True)
    run = subparsers.add_parser("run", help="collect, validate and load data once")
    run.add_argument("--source", choices=("cars", "faqs", "all"), default="all")
    run.add_argument("--mode", choices=("incremental", "initial"), default="incremental")
    run.add_argument("--input", type=Path, help="local JSON input path; --source must be cars or faqs")
    return parser.parse_args()


def main() -> int:
    """설정을 확인하고 선택한 source들을 한 번 실행한 뒤 종료 상태를 반환한다."""
    args = parse_arguments()
    if args.input and args.source == "all":
        raise SystemExit("--input requires --source cars or --source faqs")
    if args.input and not args.input.is_file():
        raise SystemExit(f"input file not found: {args.input}")
    settings = load_settings()
    configure_logging(settings)
    conn = connect_mysql(settings)
    try:
        create_tables(conn)
        results = []
        if args.source in ("cars", "all"):
            results.append(run_cars(settings, conn, args.mode, args.input))
        if args.source in ("faqs", "all"):
            results.append(run_faqs(settings, conn, args.mode, args.input))
        return 1 if any(result.error_message for result in results) else 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())


# ============================================================================
# MAIN END: 파이프라인 CLI 진입점의 끝.
# ============================================================================
