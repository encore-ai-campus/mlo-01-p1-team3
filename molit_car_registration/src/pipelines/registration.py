"""우리 자동차등록 전용 파이프라인 실행 파일."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Sequence

from collection.registration import (
    FixtureRegistrationClient,
    RegistrationApiClient,
    RegistrationCollectionError,
    current_period,
    extract_record_list,
    find_value,
    normalize_period,
    response_hash,
)
from common.config import Settings, settings_from_env
from common.contracts import CollectionEnvelope, PreparedBatch, RejectedRecord
from common.logging_utils import JsonlLogger
from loading.registration import JsonQuotaLedger, StateStore, sink_for
from preprocessing.registration import transform_records


def run_once(*, settings: Settings, fixture: Optional[Path] = None, period: Optional[str] = None, dry_run: bool = False) -> dict[str, Any]:
    run_id = str(uuid.uuid4())
    logger = JsonlLogger(settings.log_path, {"pipeline_name": "molit_car_registration", "run_id": run_id})
    state = StateStore(settings.registration_state_path)
    quota = JsonQuotaLedger(state, settings.registration_daily_quota, settings.time_zone)
    selected_period = normalize_period(period or current_period(settings.time_zone))
    logger.event("INFO", "run_started", "registration pipeline started", stage_name="Collect", period=selected_period)

    client = FixtureRegistrationClient(fixture) if fixture else RegistrationApiClient(settings)
    payload, body = client.fetch_period(selected_period, quota.reserve)
    records = extract_record_list(payload)
    status = find_value(payload, {"status_code", "statuscode"}) if isinstance(payload, dict) else None
    if not records and status not in {"INFO-200", 200, "200"}:
        raise RegistrationCollectionError("response contains no records", "response_schema")

    collected_at = datetime.now(timezone.utc).isoformat()
    envelope = CollectionEnvelope(
        source_name="molit_car_registration",
        collected_at=datetime.fromisoformat(collected_at),
        records=tuple(records),
        metadata={"period": selected_period, "response_sha256": response_hash(body)},
    )
    logger.event("INFO", "period_collected", "registration response collected", stage_name="Collect", collected_count=len(envelope.records), response_sha256=response_hash(body))

    valid, rejected = transform_records(envelope.records, period=selected_period, settings=settings, run_id=run_id, collected_at=collected_at)
    prepared = PreparedBatch(
        records=tuple(valid),
        rejected=tuple(RejectedRecord(item.index, item.error_code, "|".join(filter(None, (item.sido_name, item.sigungu_name)))) for item in rejected),
    )
    logger.event("INFO", "period_preprocessed", "registration response normalized", stage_name="Preprocess", collected_count=len(records), valid_count=len(prepared.records), rejected_count=len(prepared.rejected))
    if prepared.rejected:
        logger.event("WARNING", "records_rejected", "source rows failed validation", stage_name="Validate", rejected_count=len(prepared.rejected), reject_codes=sorted({item.error_code for item in prepared.rejected}))

    stats = {"inserted_count": 0, "updated_count": 0, "unchanged_count": 0}
    if not dry_run:
        stats = sink_for(settings, "json").save(prepared.records).__dict__
        stored = state.load()
        stored.update({"last_success_period": selected_period, "last_run_id": run_id, "last_collected_count": len(records), "last_preprocessed_count": len(prepared.records), "updated_at": datetime.now(timezone.utc).isoformat()})
        state.save(stored)

    result = {"status": "OK", "run_id": run_id, "period": selected_period, "collected_count": len(records), "preprocessed_count": len(prepared.records), "rejected_count": len(prepared.rejected), "api_calls": 1, "quota_remaining": quota.remaining, "dry_run": dry_run, **stats}
    logger.event("INFO", "run_succeeded", "registration pipeline completed", stage_name="Load", **result)
    return result


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="우리 자동차등록 Open API 파이프라인")
    parser.add_argument("--fixture", type=Path)
    parser.add_argument("--period")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    try:
        settings = settings_from_env()
        if args.output_dir:
            settings = Settings(**{**settings.__dict__, "output_dir": args.output_dir, "registration_state_path": args.output_dir / "registration_state.json", "log_path": args.output_dir / "jsonl"})
        if not args.fixture and not settings.registration_api_key:
            raise RegistrationCollectionError("MOLIT_API_KEY or REGISTRATION_API_KEY is required", "missing_api_key")
        print(json.dumps(run_once(settings=settings, fixture=args.fixture, period=args.period, dry_run=args.dry_run), ensure_ascii=False))
        return 0
    except (RegistrationCollectionError, RuntimeError, ValueError) as exc:
        print(json.dumps({"status": "FAILED", "error_code": getattr(exc, "code", "registration_error"), "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
