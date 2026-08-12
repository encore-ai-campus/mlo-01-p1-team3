"""Daily registration-report pipeline: collection -> preprocessing -> loading."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Sequence

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from collection.registration import (
    FixtureRegistrationClient,
    RegistrationApiClient,
    RegistrationError,
    current_period,
    extract_record_list,
    find_value,
    month_label,
    normalize_period,
)
from common.config import Settings, settings_from_env
from common.contracts import CollectionEnvelope, PreparedBatch, RejectedRecord
from src.logging.logging_utils import JsonlLogger
from loading.registration import (
    JsonQuotaLedger,
    JsonlRegistrationUpsertSink,
    QuotaExceeded,
    RegistrationStateStore,
    SqlQuotaLedger,
    SqlRegistrationUpsertSink,
)
from preprocessing.registration import RegistrationPreprocessError, transform_registration_records


def run_once(
    *,
    settings: Settings,
    fixture: Optional[Path] = None,
    sink_name: str = "json",
    dry_run: bool = False,
    period: Optional[str] = None,
    start_period: Optional[str] = None,
    max_calls: Optional[int] = None,
) -> Dict[str, Any]:
    """Run exactly one registration API request for the selected month.

    ``max_calls`` and ``start_period`` remain accepted as narrow migration
    shims for callers of the previous bounded entrypoint, but a daily run may
    never perform more than one upstream request.
    """

    if sink_name not in {"json", "sql"}:
        raise ValueError(f"unsupported registration sink: {sink_name}")
    if max_calls not in (None, 1):
        raise ValueError("registration pipeline performs exactly one API call per run")
    if period and start_period and normalize_period(period) != normalize_period(start_period):
        raise ValueError("period and start_period must identify the same month")

    run_id = str(uuid.uuid4())
    logger = JsonlLogger(
        settings.log_path,
        {"service": "pipeline", "pipeline_name": "vehicle_registration", "run_id": run_id},
    )
    state = RegistrationStateStore(settings.registration_state_path)
    quota: Any = (
        SqlQuotaLedger(settings)
        if sink_name == "sql"
        else JsonQuotaLedger(state, limit=settings.registration_daily_quota, time_zone=settings.time_zone)
    )
    stored_state = state.load()
    requested_period = normalize_period(
        period
        or start_period
        or settings.registration_start_period
        or current_period(settings.time_zone)
    )
    sink: Any = None
    logger.event(
        "INFO",
        "run_started",
        "daily registration run started",
        stage_name="Collect",
        logic_name="vehicle_registration.collect",
        period=month_label(requested_period),
        quota_remaining=quota.remaining,
    )

    total_collected = total_preprocessed = total_valid = total_rejected = 0
    total_inserted = total_updated = total_unchanged = 0
    api_calls_before = quota.used_count
    collected = False
    try:
        client: Any = FixtureRegistrationClient(fixture) if fixture else RegistrationApiClient(settings)
        if not dry_run:
            if sink_name == "json":
                sink = JsonlRegistrationUpsertSink(settings.output_dir / "vehicle_registration_reports.jsonl")
            else:
                sink = SqlRegistrationUpsertSink(settings)

        if quota.remaining > 0:
            payload, body = client.fetch_period(requested_period, reserve_call=quota.reserve)
            records = extract_record_list(payload)
            status = find_value(payload, {"status_code", "statuscode"}) if isinstance(payload, dict) else None
            if not records and status not in {"INFO-200", 200, "200"} and not isinstance(payload, dict):
                raise RegistrationError("registration response has no record envelope", code="response_schema")
            collected = True
            envelope = CollectionEnvelope(
                source_name="vehicle_registration",
                collected_at=datetime.now(timezone.utc),
                records=tuple(records),
                metadata={
                    "period": requested_period,
                    "response_sha256": hashlib.sha256(body).hexdigest(),
                },
            )
            total_collected = len(envelope.records)
            logger.event(
                "INFO",
                "period_collected",
                "registration response collected",
                stage_name="Collect",
                logic_name="vehicle_registration.collect",
                period=month_label(requested_period),
                collected_count=len(envelope.records),
                response_sha256=hashlib.sha256(body).hexdigest(),
            )

            valid, rejected = transform_registration_records(
                envelope.records,
                period=requested_period,
                settings=settings,
                run_id=run_id,
                collected_at=envelope.collected_at.isoformat(),
            )
            prepared = PreparedBatch(
                records=tuple(valid),
                rejected=tuple(
                    RejectedRecord(
                        index=item.index,
                        error_code=item.error_code,
                        stable_key="|".join(
                            filter(None, (item.sido_name, item.sigungu_name, item.vehicle_type, item.usage_type))
                        ),
                    )
                    for item in rejected
                ),
            )
            total_preprocessed = len(prepared.records)
            total_valid = len(prepared.records)
            total_rejected = len(prepared.rejected)
            logger.event(
                "INFO",
                "period_preprocessed",
                "registration response flattened into normalized measures",
                stage_name="Preprocess",
                logic_name="vehicle_registration.preprocess",
                period=month_label(requested_period),
                collected_count=len(envelope.records),
                preprocessed_count=len(prepared.records),
                valid_count=len(prepared.records),
                rejected_count=len(prepared.rejected),
                response_sha256=hashlib.sha256(body).hexdigest(),
            )
            if prepared.rejected:
                logger.event(
                    "WARNING",
                    "records_rejected",
                    "registration source rows failed validation",
                    stage_name="Validate",
                    logic_name="vehicle_registration.validate",
                    rejected_count=len(prepared.rejected),
                    reject_codes=sorted({item.error_code for item in prepared.rejected}),
                )
            if sink is not None:
                stats = sink.save(prepared.records)
                total_inserted = stats.inserted_count
                total_updated = stats.updated_count
                total_unchanged = stats.unchanged_count

            stored_state = state.load()
            stored_state.update(
                {
                    "last_success_period": requested_period,
                    "last_run_id": run_id,
                    "last_collected_count": total_collected,
                    "last_preprocessed_count": total_preprocessed,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }
            )
            if not dry_run:
                state.save(stored_state)

        result = {
            "status": "OK",
            "run_id": run_id,
            "period": month_label(requested_period) if collected else None,
            "periods": 1 if collected else 0,
            "collected_count": total_collected,
            "preprocessed_count": total_preprocessed,
            "valid_count": total_valid,
            "rejected_count": total_rejected,
            "inserted_count": total_inserted,
            "updated_count": total_updated,
            "unchanged_count": total_unchanged,
            "api_calls": quota.used_count - api_calls_before,
            "quota_used": quota.used_count,
            "quota_remaining": quota.remaining,
            "dry_run": dry_run,
        }
        logger.event(
            "INFO",
            "run_succeeded",
            "daily registration run completed",
            stage_name="Load",
            logic_name="vehicle_registration.load",
            **result,
        )
        return result
    except (RegistrationError, QuotaExceeded, RegistrationPreprocessError, RuntimeError, ValueError) as exc:
        logger.event(
            "ERROR",
            "run_failed",
            "registration run failed",
            stage_name="Collect",
            logic_name="vehicle_registration.collect",
            error_code=getattr(exc, "code", "registration_error"),
            quota_used=quota.used_count,
        )
        raise
    finally:
        close = getattr(sink, "close", None)
        if close:
            close()
        close_quota = getattr(quota, "close", None)
        if close_quota:
            close_quota()


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Run one daily registration-report collection")
    parser.add_argument("--fixture", type=Path)
    parser.add_argument("--sink", choices=("json", "sql"), default="json")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--period", "--start-period", dest="period")
    parser.add_argument("--max-calls", type=int, help=argparse.SUPPRESS)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    try:
        settings = settings_from_env()
        if args.output_dir:
            settings = Settings(
                **{
                    **settings.__dict__,
                    "output_dir": args.output_dir,
                    "log_path": args.output_dir / "jsonl",
                    "registration_state_path": args.output_dir / "registration_state.json",
                }
            )
        result = run_once(
            settings=settings,
            fixture=args.fixture,
            sink_name=args.sink,
            dry_run=args.dry_run,
            period=args.period,
            max_calls=args.max_calls,
        )
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except (RegistrationError, RegistrationPreprocessError, RuntimeError, ValueError) as exc:
        print(
            json.dumps({"status": "FAILED", "error_code": getattr(exc, "code", "registration_error")}),
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
