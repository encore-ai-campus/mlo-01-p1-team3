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

from collection.api import ApiError
from collection.usedcar import FetchError, load_fetcher, page_checkpoint
from common.config import Settings, settings_from_env
from common.logging_utils import JsonlLogger
from common.contracts import CollectionEnvelope, PreparedBatch, RejectedRecord
from common.time_utils import utc_now_iso
from loading.usedcar import CheckpointStore, sink_for
from preprocessing.usedcar import PreprocessError, transform_records


def _require_incremental_contract(page_state: Mapping[str, Any]) -> int:
    """Fail closed when the source cannot provide the next after_seq value."""

    value = page_state.get("high_water_seq")
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
        {"service": "data_preprocessing", "pipeline_name": "used_car", "run_id": run_id},
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
    current_stage = "Collect"
    current_logic = "used_car.collect"
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
            selected_mode = "incremental" if checkpoint.get("initialized") else "initial"
        if selected_mode not in {"initial", "incremental"}:
            raise ValueError("mode must be auto, initial, or incremental")
        last_checkpoint = dict(checkpoint)
        logger.event("INFO", "run_started", "one-shot used-car run started", mode=selected_mode)
        if selected_mode == "incremental":
            after_seq = int(checkpoint.get("after_seq") or 0)
            page_iterator = fetcher.iter_incremental(after_seq, settings.batch_size, settings.max_batches)
        else:
            page_iterator = fetcher.iter_initial(settings.batch_size, settings.max_batches)

        for page in page_iterator:
            batches += 1
            batch_run_id = str(uuid.uuid4())
            batch_started_at = utc_now_iso()
            page_meta = page.meta
            page_state = page_checkpoint(page_meta, page.records)
            page_epoch = page_state.get("dataset_epoch")
            stored_epoch = last_checkpoint.get("dataset_epoch")
            if stored_epoch and page_epoch and stored_epoch != page_epoch:
                raise FetchError("dataset_epoch changed; checkpoint was not advanced", code="dataset_epoch_changed")
            raw_next_seq = page_state.get("high_water_seq")
            if selected_mode == "incremental":
                next_seq = _require_incremental_contract(page_state)
            elif isinstance(raw_next_seq, int) and not isinstance(raw_next_seq, bool) and raw_next_seq >= 0:
                next_seq = raw_next_seq
            else:
                next_seq = None
                missing_incremental_contract = True

            next_checkpoint = {
                **last_checkpoint,
                "initialized": True,
                "mode": selected_mode,
                "dataset_epoch": page_epoch or last_checkpoint.get("dataset_epoch"),
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
                    dataset_epoch=page_epoch or stored_epoch,
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
                    RejectedRecord(index=item.index, error_code=item.error_code, stable_key=item.record_id)
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
                    "WARNING",
                    "records_rejected",
                    "one or more source records were rejected",
                    stage_name="Validate",
                    logic_name="used_car.validate",
                    rejected_count=len(prepared.rejected),
                    reject_codes=sorted({item.error_code for item in prepared.rejected}),
                )
            current_stage = "Load"
            current_logic = "used_car.load"
            batch_inserted = batch_updated = batch_unchanged = 0
            if sink is not None:
                if sink_name == "sql":
                    stats = sink.save(
                        prepared.records,
                        checkpoint=(
                            next_checkpoint
                            if next_seq is not None and not missing_incremental_contract
                            else None
                        ),
                        run_id=batch_run_id,
                        started_at=batch_started_at,
                    )
                else:
                    stats = sink.save(prepared.records)
                batch_inserted = stats.inserted_count
                batch_updated = stats.updated_count
                batch_unchanged = stats.unchanged_count
                total_inserted += batch_inserted
                total_updated += batch_updated
                total_unchanged += batch_unchanged

            last_checkpoint = next_checkpoint
            if not dry_run and next_seq is not None and not missing_incremental_contract:
                checkpoint_store.save(last_checkpoint)
            logger.event(
                "INFO",
                "load_skipped" if dry_run else "batch_committed",
                "batch load skipped in dry-run" if dry_run else "batch load and checkpoint completed",
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
        result = {
            "status": "OK",
            "run_id": run_id,
            "mode": selected_mode,
            "batches": batches,
            "collected_count": total_collected,
            "preprocessed_count": total_valid + total_rejected,
            "valid_count": total_valid,
            "rejected_count": total_rejected,
            "inserted_count": 0 if dry_run else total_inserted,
            "updated_count": 0 if dry_run else total_updated,
            "unchanged_count": 0 if dry_run else total_unchanged,
            "dry_run": dry_run,
            "checkpoint_path": str(settings.state_path),
        }
        logger.event("INFO", "run_succeeded", "one-shot used-car run completed", **result)
        return result
    except (ApiError, FetchError, PreprocessError, RuntimeError, ValueError) as exc:
        logger.event(
            "ERROR",
            "run_failed",
            "one-shot used-car run failed",
            stage_name=current_stage,
            logic_name=current_logic,
            error_code=getattr(exc, "code", "run_failed"),
        )
        raise
    finally:
        close = getattr(sink, "close", None)
        if close:
            close()


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Run exactly one bounded used-car collection/preprocessing cycle")
    parser.add_argument("--mode", choices=("auto", "initial", "incremental"), default="auto")
    parser.add_argument("--fixture", type=Path, help="Use a local response fixture instead of the API")
    parser.add_argument("--output-dir", type=Path, help="Override local JSONL/checkpoint directory")
    parser.add_argument("--sink", choices=("json", "sql"), default="json")
    parser.add_argument("--dry-run", action="store_true", help="Transform and validate without loading")
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
        result = run_once(settings=settings, mode=args.mode, fixture=args.fixture, sink_name=args.sink, dry_run=args.dry_run)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except (ApiError, FetchError, PreprocessError, RuntimeError, ValueError) as exc:
        print(json.dumps({"status": "FAILED", "error_code": getattr(exc, "code", "run_failed")}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
