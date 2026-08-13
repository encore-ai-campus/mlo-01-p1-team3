"""Used-car business pipeline: cursor/change collection -> loading.

The pipeline owns the source business contract for the AutoData Lab API:
initial cursor and incremental ``after_seq`` modes, sequential one-second
requests, a maximum page size of 500, stable listing identity, dataset epoch
consistency, and a checkpoint that advances only after a successful load.
Source response validation and relational normalization remain in their stage
packages; this module decides the run mode and checkpoint policy.
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from collection.usedcar import FetchError, load_fetcher, page_checkpoint
from common.config import Settings, settings_from_env
from common.logging_utils import JsonlLogger
from common.contracts import CollectionEnvelope, PreparedBatch, RejectedRecord
from common.time_utils import utc_now_iso
from loading.usedcar import CheckpointStore, sink_for
from preprocessing.usedcar import PreprocessError, transform_records


def _require_incremental_contract(
    page_state: Mapping[str, Any], *, committed_seq: int = 0
) -> int:
    """Return the processed sequence, preserving a steady-state checkpoint."""

    value = page_state.get("high_water_seq")
    if value is None and not page_state.get("records_present", True):
        boundary = page_state.get("until_seq")
        if (
            isinstance(boundary, int)
            and not isinstance(boundary, bool)
            and boundary >= committed_seq
        ):
            return committed_seq
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise FetchError(
            "source does not provide a sequence checkpoint for incremental loading",
            code="incremental_contract_missing",
        )
    return value


def run_once(
    *,
    settings: Settings,
    mode: str = "auto",
    fixture: Optional[Path] = None,
    sink_name: str = "json",
    dry_run: bool = False,
    run_id: Optional[str] = None,
) -> Dict[str, Any]:
    if sink_name not in {"json", "sql"}:
        raise ValueError(f"unsupported used-car sink: {sink_name}")
    run_id = run_id or str(uuid.uuid4())
    logger = JsonlLogger(
        settings.log_path,
        {
            "service": "data_preprocessing",
            "pipeline_name": "used_car",
            "run_id": run_id,
        },
    )
    checkpoint_store = CheckpointStore(settings.state_path)
    selected_mode = mode
    sink = None
    total_collected = total_valid = total_rejected = 0
    total_inserted = total_updated = total_unchanged = 0
    batches = 0
    checkpoint: Dict[str, Any] = {}
    last_checkpoint: Dict[str, Any] = {}
    missing_incremental_contract = False
    initial_watermark: Dict[str, Any] = {}
    last_batch_run_id: Optional[str] = None
    last_batch_started_at: Optional[str] = None
    last_batch_counts: Dict[str, int] = {}
    last_batch_stats = None
    current_stage = "Collect"
    current_logic = "used_car.collect"
    sink_close_attempted = False
    sink_close_failed = False
    fetcher = None
    fetcher_close_attempted = False
    fetcher_close_failed = False

    def close_sink() -> None:
        nonlocal sink_close_attempted, sink_close_failed
        if sink_close_attempted:
            return
        sink_close_attempted = True
        close = getattr(sink, "close", None)
        if close:
            try:
                close()
            except Exception:
                sink_close_failed = True
                raise

    def close_fetcher() -> None:
        nonlocal fetcher_close_attempted, fetcher_close_failed
        if fetcher_close_attempted:
            return
        fetcher_close_attempted = True
        close = getattr(fetcher, "close", None)
        if close:
            try:
                close()
            except Exception:
                fetcher_close_failed = True
                raise

    try:
        fetcher = load_fetcher(settings, fixture)
        sink = None if dry_run else sink_for(settings, sink_name)
        if sink_name == "sql" and sink is not None:
            sql_checkpoint = sink.load_checkpoint()
            if sql_checkpoint:
                checkpoint = sql_checkpoint
            else:
                checkpoint = checkpoint_store.load()
        else:
            checkpoint = checkpoint_store.load()
        selected_mode = mode
        if selected_mode == "auto":
            selected_mode = (
                "incremental" if checkpoint.get("initialized") else "initial"
            )
        if selected_mode not in {"initial", "incremental"}:
            raise ValueError("mode must be auto, initial, or incremental")
        last_checkpoint = dict(checkpoint)
        if selected_mode == "initial":
            initial_watermark = fetcher.incremental_watermark()
        logger.event(
            "INFO", "run_started", "one-shot used-car run started", mode=selected_mode
        )
        if selected_mode == "incremental":
            after_seq = int(checkpoint.get("after_seq") or 0)
            page_iterator = fetcher.iter_incremental(
                after_seq, settings.batch_size, settings.max_batches
            )
        else:
            page_iterator = fetcher.iter_initial(
                settings.batch_size, settings.max_batches
            )

        for page in page_iterator:
            batches += 1
            batch_run_id = str(uuid.uuid4())
            batch_started_at = utc_now_iso()
            last_batch_run_id = batch_run_id
            last_batch_started_at = batch_started_at
            page_meta = page.meta
            page_state = page_checkpoint(page_meta, page.records)
            page_state["records_present"] = bool(page.records)
            page_epoch = page_state.get("dataset_epoch")
            watermark_epoch = initial_watermark.get("dataset_epoch")
            if page_epoch and watermark_epoch and page_epoch != watermark_epoch:
                raise FetchError(
                    "dataset_epoch changed between initial snapshot and change watermark",
                    code="dataset_epoch_changed",
                )
            stored_epoch = last_checkpoint.get("dataset_epoch")
            if stored_epoch and page_epoch and stored_epoch != page_epoch:
                raise FetchError(
                    "dataset_epoch changed; checkpoint was not advanced",
                    code="dataset_epoch_changed",
                )
            raw_next_seq = page_state.get("high_water_seq")
            if selected_mode == "incremental":
                committed_value = last_checkpoint.get("after_seq")
                committed_seq = (
                    committed_value
                    if isinstance(committed_value, int)
                    and not isinstance(committed_value, bool)
                    and committed_value >= 0
                    else 0
                )
                next_seq = _require_incremental_contract(
                    page_state, committed_seq=committed_seq
                )
            elif isinstance(initial_watermark.get("high_water_seq"), int):
                next_seq = int(initial_watermark["high_water_seq"])
            elif (
                isinstance(raw_next_seq, int)
                and not isinstance(raw_next_seq, bool)
                and raw_next_seq >= 0
            ):
                next_seq = raw_next_seq
            else:
                next_seq = None
                missing_incremental_contract = True
            committed_seq = last_checkpoint.get("after_seq")
            if (
                next_seq is not None
                and last_checkpoint.get("initialized")
                and isinstance(committed_seq, int)
                and not isinstance(committed_seq, bool)
                and next_seq < committed_seq
            ):
                raise FetchError(
                    "source sequence is older than the committed checkpoint",
                    code="checkpoint_regression",
                )

            next_checkpoint = {
                **last_checkpoint,
                "initialized": True,
                "mode": selected_mode,
                "dataset_epoch": (
                    page_epoch
                    or watermark_epoch
                    or last_checkpoint.get("dataset_epoch")
                ),
                "updated_at": utc_now_iso(),
            }
            if next_seq is not None:
                next_checkpoint["after_seq"] = next_seq
            if page_state.get("until_id") is not None:
                next_checkpoint["after_id"] = page_state["until_id"]

            envelope = CollectionEnvelope(
                source_name="used_car",
                collected_at=datetime.now(timezone.utc),
                records=tuple(page.records),
                metadata={"mode": selected_mode, "batch_number": batches, **page_state},
            )
            total_collected += len(envelope.records)
            logger.event(
                "INFO",
                "batch_collected",
                "used-car batch collected",
                stage_name="Collect",
                logic_name="used_car.collect",
                batch_number=batches,
                collected_count=len(envelope.records),
            )
            current_stage = "Preprocess"
            current_logic = "used_car.preprocess"
            try:
                valid_rows, rejected = transform_records(
                    envelope.records,
                    settings=settings,
                    run_id=run_id,
                    dataset_epoch=page_epoch or watermark_epoch or stored_epoch,
                )
            except Exception as exc:
                logger.event(
                    "ERROR",
                    "preprocess_failed",
                    "used-car records could not be transformed",
                    stage_name="Preprocess",
                    logic_name="used_car.preprocess",
                    error_code=getattr(exc, "code", "preprocess_failed"),
                    batch_number=batches,
                )
                raise
            prepared = PreparedBatch(
                records=tuple(valid_rows),
                rejected=tuple(
                    RejectedRecord(
                        index=item.index,
                        error_code=item.error_code,
                        stable_key=item.record_id,
                    )
                    for item in rejected
                ),
            )
            total_valid += len(prepared.records)
            total_rejected += len(prepared.rejected)
            logger.event(
                "INFO",
                "batch_preprocessed",
                "batch transformed and validated",
                stage_name="Preprocess",
                logic_name="used_car.preprocess",
                batch_number=batches,
                collected_count=len(envelope.records),
                valid_count=len(prepared.records),
                rejected_count=len(prepared.rejected),
            )
            current_stage = "Validate"
            current_logic = "used_car.validate"
            logger.event(
                "INFO",
                "validation_completed",
                "used-car record validation completed",
                stage_name="Validate",
                logic_name="used_car.validate",
                batch_number=batches,
                input_count=len(envelope.records),
                valid_count=len(prepared.records),
                rejected_count=len(prepared.rejected),
            )
            if prepared.rejected:
                logger.event(
                    "ERROR",
                    "records_rejected",
                    "one or more source records were rejected and discarded",
                    stage_name="Validate",
                    logic_name="used_car.validate",
                    error_code="records_rejected",
                    rejected_count=len(prepared.rejected),
                    discarded_count=len(prepared.rejected),
                    discard_policy="log_only",
                    reject_codes=sorted(
                        {item.error_code for item in prepared.rejected}
                    ),
                )
            if envelope.records and not prepared.records and prepared.rejected:
                raise PreprocessError(
                    "all collected used-car records were rejected; checkpoint was not advanced",
                    code="all_records_rejected",
                )
            current_stage = "Load"
            current_logic = "used_car.load"
            batch_inserted = batch_updated = batch_unchanged = 0
            if sink is not None:
                last_batch_counts = {
                    "collected_count": len(envelope.records),
                    "preprocessed_count": len(prepared.records)
                    + len(prepared.rejected),
                    "valid_count": len(prepared.records),
                    "rejected_count": len(prepared.rejected),
                    "api_calls": 1,
                }
                if sink_name == "sql":
                    stats = sink.save(
                        prepared.records,
                        checkpoint=(
                            next_checkpoint
                            if selected_mode == "incremental"
                            and next_seq is not None
                            and not missing_incremental_contract
                            else None
                        ),
                        run_id=batch_run_id,
                        started_at=batch_started_at,
                        run_counts=last_batch_counts,
                    )
                else:
                    stats = sink.save(prepared.records)
                batch_inserted = stats.inserted_count
                batch_updated = stats.updated_count
                batch_unchanged = stats.unchanged_count
                last_batch_stats = stats
                total_inserted += batch_inserted
                total_updated += batch_updated
                total_unchanged += batch_unchanged

            last_checkpoint = next_checkpoint
            if (
                not dry_run
                and selected_mode == "incremental"
                and next_seq is not None
                and not missing_incremental_contract
            ):
                checkpoint_store.save(last_checkpoint)
            logger.event(
                "INFO",
                "load_skipped" if dry_run else "batch_committed",
                "batch load skipped in dry-run"
                if dry_run
                else "batch load and checkpoint completed",
                stage_name="Load",
                logic_name="used_car.load",
                batch_number=batches,
                inserted_count=batch_inserted,
                updated_count=batch_updated,
                unchanged_count=batch_unchanged,
                load_skipped=dry_run,
                checkpoint={
                    "after_id": last_checkpoint.get("after_id"),
                    "after_seq": last_checkpoint.get("after_seq"),
                    "dataset_epoch": last_checkpoint.get("dataset_epoch"),
                },
            )
        if selected_mode == "initial" and missing_incremental_contract:
            raise FetchError(
                "initial sync completed without an incremental checkpoint contract",
                code="incremental_contract_missing",
            )
        if selected_mode == "initial" and not dry_run and initial_watermark:
            final_checkpoint = {
                **last_checkpoint,
                "initialized": True,
                "mode": "initial",
                "after_seq": int(initial_watermark["high_water_seq"]),
                "dataset_epoch": (
                    initial_watermark.get("dataset_epoch")
                    or last_checkpoint.get("dataset_epoch")
                ),
                "updated_at": utc_now_iso(),
            }
            if sink_name == "sql" and sink is not None:
                final_run_counts = dict(last_batch_counts)
                final_run_counts["api_calls"] = final_run_counts.get("api_calls", 0) + 1
                sink.save(
                    (),
                    checkpoint=final_checkpoint,
                    run_id=last_batch_run_id or str(uuid.uuid4()),
                    started_at=last_batch_started_at or utc_now_iso(),
                    run_counts=final_run_counts or {"api_calls": 1},
                    record_stats=last_batch_stats,
                )
            checkpoint_store.save(final_checkpoint)
            last_checkpoint = final_checkpoint
        result = {
            "status": "OK",
            "run_id": run_id,
            "mode": selected_mode,
            "batches": batches,
            "collected_count": total_collected,
            "preprocessed_count": total_valid + total_rejected,
            "valid_count": total_valid,
            "rejected_count": total_rejected,
            "api_calls": batches + (1 if selected_mode == "initial" else 0),
            "inserted_count": 0 if dry_run else total_inserted,
            "updated_count": 0 if dry_run else total_updated,
            "unchanged_count": 0 if dry_run else total_unchanged,
            "dry_run": dry_run,
            "checkpoint_path": str(settings.state_path),
        }
        close_sink()
        close_fetcher()
        logger.event(
            "INFO", "run_succeeded", "one-shot used-car run completed", **result
        )
        return result
    except Exception as exc:
        logger.event(
            "ERROR",
            "run_failed",
            "one-shot used-car run failed",
            stage_name=current_stage,
            logic_name=current_logic,
            error_code=(
                "resource_close_failed"
                if sink_close_failed or fetcher_close_failed
                else getattr(exc, "code", "run_failed")
            ),
        )
        raise
    finally:
        if not sink_close_attempted:
            try:
                close_sink()
            except Exception:
                try:
                    logger.event(
                        "ERROR",
                        "resource_close_failed",
                        "used-car sink could not be closed cleanly",
                        stage_name=current_stage,
                        logic_name=current_logic,
                        error_code="resource_close_failed",
                    )
                except Exception:
                    pass
        if not fetcher_close_attempted:
            try:
                close_fetcher()
            except Exception:
                try:
                    logger.event(
                        "ERROR",
                        "resource_close_failed",
                        "used-car fetcher could not be closed cleanly",
                        stage_name=current_stage,
                        logic_name=current_logic,
                        error_code="resource_close_failed",
                    )
                except Exception:
                    pass


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run exactly one bounded used-car collection/preprocessing cycle"
    )
    parser.add_argument(
        "--mode", choices=("auto", "initial", "incremental"), default="auto"
    )
    parser.add_argument(
        "--fixture", type=Path, help="Use a local response fixture instead of the API"
    )
    parser.add_argument(
        "--output-dir", type=Path, help="Override local JSONL/checkpoint directory"
    )
    parser.add_argument("--sink", choices=("json", "sql"), default="json")
    parser.add_argument(
        "--dry-run", action="store_true", help="Transform and validate without loading"
    )
    args = parser.parse_args(argv)
    try:
        settings = settings_from_env()
        if args.output_dir:
            settings = Settings(
                **{
                    **settings.__dict__,
                    "output_dir": args.output_dir,
                    "state_path": args.output_dir / "usedcar_checkpoint.json",
                    "log_path": args.output_dir / "jsonl",
                }
            )
        result = run_once(
            settings=settings,
            mode=args.mode,
            fixture=args.fixture,
            sink_name=args.sink,
            dry_run=args.dry_run,
        )
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except Exception as exc:
        print(
            json.dumps(
                {"status": "FAILED", "error_code": getattr(exc, "code", "run_failed")}
            ),
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
