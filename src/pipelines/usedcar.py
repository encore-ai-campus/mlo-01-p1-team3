"""Used-car pipeline orchestration: collection -> preprocessing -> loading."""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from collection.api import ApiClient, ApiError
from collection.usedcar import FetchError, load_fetcher, page_checkpoint
from common.config import Settings, settings_from_env
from common.logging_utils import JsonlLogger
from common.contracts import CollectionEnvelope, PreparedBatch, RejectedRecord
from loading.usedcar import CheckpointStore, LoadStats, sink_for
from preprocessing.usedcar import PreprocessError, transform_records


def _extract_last_seq(records: Sequence[Mapping[str, Any]]) -> Optional[int]:
    values = [record.get("seq") for record in records if isinstance(record.get("seq"), int)]
    return max(values) if values else None


def run_once(
    *, settings: Settings, mode: str = "auto", fixture: Optional[Path] = None, sink_name: str = "json", dry_run: bool = False
) -> Dict[str, Any]:
    run_id = str(uuid.uuid4())
    logger = JsonlLogger(
        settings.log_path,
        {"service": "data_preprocessing", "pipeline_name": "used_car", "run_id": run_id},
    )
    checkpoint_store = CheckpointStore(settings.state_path)
    checkpoint = checkpoint_store.load()
    selected_mode = mode
    if selected_mode == "auto":
        selected_mode = "incremental" if checkpoint.get("initialized") else "initial"
    if selected_mode not in {"initial", "incremental"}:
        raise ValueError("mode must be auto, initial, or incremental")

    logger.event("INFO", "run_started", "one-shot used-car run started", mode=selected_mode)
    sink = None
    total_collected = total_valid = total_rejected = 0
    total_inserted = total_updated = total_unchanged = 0
    batches = 0
    last_checkpoint: Dict[str, Any] = dict(checkpoint)
    try:
        fetcher = load_fetcher(settings, fixture)
        sink = None if dry_run else sink_for(settings, sink_name)
        if selected_mode == "incremental":
            after_seq = int(checkpoint.get("after_seq") or 0)
            page_iterator = fetcher.iter_incremental(after_seq, settings.batch_size, settings.max_batches)
        else:
            page_iterator = fetcher.iter_initial(settings.batch_size, settings.max_batches)

        for page in page_iterator:
            batches += 1
            page_meta = page.meta
            page_state = page_checkpoint(page_meta, page.records)
            page_epoch = page_state.get("dataset_epoch")
            stored_epoch = checkpoint.get("dataset_epoch")
            if stored_epoch and page_epoch and stored_epoch != page_epoch:
                raise FetchError("dataset_epoch changed; checkpoint was not advanced", code="dataset_epoch_changed")

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
            valid_rows, rejected = transform_records(
                envelope.records,
                settings=settings,
                run_id=run_id,
                dataset_epoch=page_epoch or stored_epoch,
            )
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
            if sink is not None:
                stats = sink.save(prepared.records)
                total_inserted += stats.inserted_count
                total_updated += stats.updated_count
                total_unchanged += stats.unchanged_count

            last_checkpoint = {
                **last_checkpoint,
                "initialized": True,
                "mode": selected_mode,
                "dataset_epoch": page_state.get("dataset_epoch") or last_checkpoint.get("dataset_epoch"),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            if selected_mode == "initial":
                if page_state.get("until_id") is not None:
                    last_checkpoint["after_id"] = page_state["until_id"]
                last_checkpoint["after_seq"] = page_state.get("high_water_seq") or last_checkpoint.get("after_seq", 0)
            else:
                next_seq = page_state.get("high_water_seq") or _extract_last_seq(page.records)
                if next_seq is not None:
                    last_checkpoint["after_seq"] = int(next_seq)
            if not dry_run:
                checkpoint_store.save(last_checkpoint)
            logger.event(
                "INFO",
                "batch_committed",
                "batch load and checkpoint completed",
                stage_name="Load",
                logic_name="used_car.load",
                batch_number=batches,
                inserted_count=0 if dry_run else total_inserted,
                updated_count=0 if dry_run else total_updated,
                unchanged_count=0 if dry_run else total_unchanged,
                checkpoint={
                    "after_id": last_checkpoint.get("after_id"),
                    "after_seq": last_checkpoint.get("after_seq"),
                    "dataset_epoch": last_checkpoint.get("dataset_epoch"),
                },
            )
        result = {
            "status": "OK",
            "run_id": run_id,
            "mode": selected_mode,
            "batches": batches,
            "collected_count": total_collected,
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
        logger.event("ERROR", "run_failed", "one-shot used-car run failed", error_code=getattr(exc, "code", "run_failed"))
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
