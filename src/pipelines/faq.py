"""FAQ business pipeline: bounded collection -> validation -> loading.

This module owns the FAQ run-level business contract in addition to composing
the stage packages. The current baseline requires an allow-listed source,
at least one second between requests, no more than two pages, and no more
than ten questions per page. Prepared documents retain identity, question,
answer, category, source URL, license, attribution, and content hash.
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from collection.faq import FaqCollector, FaqError, fixture_pages
from common.config import Settings, settings_from_env
from common.logging_utils import JsonlLogger
from common.contracts import CollectionEnvelope, PreparedBatch, RejectedRecord
from loading.faq import FaqLoadStats, JsonlFaqUpsertSink, MongoFaqUpsertSink
from preprocessing.faq import (
    FaqPreprocessError,
    transform_faq_records,
)


FAQ_MAX_PAGES = 2
FAQ_MAX_QUESTIONS_PER_PAGE = 10
FAQ_MIN_INTERVAL_SECONDS = 1.0


def _validate_business_requirements(settings: Settings) -> None:
    max_pages = int(getattr(settings, "faq_max_pages", FAQ_MAX_PAGES))
    if not 1 <= max_pages <= FAQ_MAX_PAGES:
        raise ValueError(f"FAQ_MAX_PAGES must be between 1 and {FAQ_MAX_PAGES}")
    interval_seconds = float(getattr(settings, "faq_interval_seconds", FAQ_MIN_INTERVAL_SECONDS))
    if interval_seconds < FAQ_MIN_INTERVAL_SECONDS:
        raise ValueError("FAQ_INTERVAL_SECONDS must be at least 1 second")
    max_questions = int(
        getattr(settings, "faq_max_questions_per_page", FAQ_MAX_QUESTIONS_PER_PAGE)
    )
    if not 1 <= max_questions <= FAQ_MAX_QUESTIONS_PER_PAGE:
        raise ValueError(
            f"FAQ_MAX_QUESTIONS_PER_PAGE must be between 1 and {FAQ_MAX_QUESTIONS_PER_PAGE}"
        )


def run_once(
    *,
    settings: Settings,
    fixture: Optional[Path] = None,
    sink_name: str = "json",
    dry_run: bool = False,
    run_id: Optional[str] = None,
) -> Dict[str, Any]:
    _validate_business_requirements(settings)
    if sink_name not in {"json", "mongo"}:
        raise ValueError(f"unsupported FAQ sink: {sink_name}")
    run_id = run_id or str(uuid.uuid4())
    logger = JsonlLogger(
        settings.log_path,
        {"service": "data_preprocessing", "pipeline_name": "faq", "run_id": run_id},
    )
    collected_at = datetime.now(timezone.utc)
    logger.event("INFO", "run_started", "FAQ run started", stage_name="Collect", logic_name="faq.collect")
    raw_records: List[Dict[str, Any]] = []
    page_count = 0
    response_hashes: List[str] = []
    try:
        pages = fixture_pages(fixture) if fixture else FaqCollector(settings).iter_pages()
        for page in pages:
            page_count += 1
            if page_count > FAQ_MAX_PAGES:
                raise FaqError("FAQ page limit exceeded", code="faq_page_limit")
            max_questions = int(
                getattr(settings, "faq_max_questions_per_page", FAQ_MAX_QUESTIONS_PER_PAGE)
            )
            if len(page.records) > max_questions:
                raise FaqError("FAQ question limit exceeded", code="faq_question_limit")
            response_hashes.append(page.response_sha256)
            raw_records.extend(page.records)
    except Exception as exc:
        logger.event(
            "ERROR",
            "collection_failed",
            "FAQ HTML collection failed",
            stage_name="Collect",
            logic_name="faq.collect",
            error_code=getattr(exc, "code", "collection_failed"),
        )
        raise
    envelope = CollectionEnvelope(
        source_name="faq",
        collected_at=collected_at,
        records=tuple(raw_records),
        metadata={"page_count": page_count, "response_sha256": tuple(response_hashes)},
    )
    logger.event(
        "INFO",
        "collection_completed",
        "FAQ HTML collection completed",
        stage_name="Collect",
        logic_name="faq.collect",
        page_count=page_count,
        collected_count=len(envelope.records),
        response_sha256=response_hashes,
    )
    try:
        valid, rejected = transform_faq_records(
            envelope.records,
            settings=settings,
            run_id=run_id,
            collected_at=collected_at.isoformat(),
        )
    except Exception as exc:
        logger.event(
            "ERROR",
            "preprocess_failed",
            "FAQ records could not be transformed",
            stage_name="Preprocess",
            logic_name="faq.preprocess",
            error_code=getattr(exc, "code", "preprocess_failed"),
        )
        raise
    prepared = PreparedBatch(
        records=tuple(valid),
        rejected=tuple(
            RejectedRecord(index=item.index, error_code=item.error_code, stable_key=item.faq_id)
            for item in rejected
        ),
    )
    logger.event(
        "INFO",
        "preprocess_completed",
        "FAQ documents transformed",
        stage_name="Preprocess",
        logic_name="faq.preprocess",
        preprocessed_count=len(prepared.records),
        rejected_count=len(prepared.rejected),
    )
    logger.event(
        "INFO",
        "validation_completed",
        "FAQ record validation completed",
        stage_name="Validate",
        logic_name="faq.validate",
        input_count=len(envelope.records),
        valid_count=len(prepared.records),
        rejected_count=len(prepared.rejected),
    )
    if prepared.rejected:
        logger.event(
            "WARNING",
            "records_rejected",
            "FAQ records failed validation",
            stage_name="Validate",
            logic_name="faq.validate",
            rejected_count=len(prepared.rejected),
            reject_codes=sorted({item.error_code for item in prepared.rejected}),
        )
    sink: Any = None
    try:
        if not dry_run:
            if sink_name == "json":
                sink = JsonlFaqUpsertSink(settings.output_dir / "faq.jsonl")
            elif sink_name == "mongo":
                sink = MongoFaqUpsertSink(settings)
            stats = sink.save(prepared.records)
        else:
            stats = FaqLoadStats()
        result = {
            "status": "OK",
            "run_id": run_id,
            "mode": "bounded",
            "pages": page_count,
            "collected_count": len(envelope.records),
            "preprocessed_count": len(prepared.records) + len(prepared.rejected),
            "valid_count": len(prepared.records),
            "rejected_count": len(prepared.rejected),
            "inserted_count": stats.inserted_count,
            "updated_count": stats.updated_count,
            "unchanged_count": stats.unchanged_count,
            "dry_run": dry_run,
            "checkpoint_path": None,
        }
        logger.event("INFO", "run_succeeded", "FAQ run completed", stage_name="Load", logic_name="faq.load", **result)
        return result
    except Exception as exc:
        logger.event(
            "ERROR",
            "run_failed",
            "FAQ run failed",
            stage_name="Load",
            logic_name="faq.load",
            error_code=getattr(exc, "code", "load_failed"),
        )
        raise
    finally:
        close = getattr(sink, "close", None)
        if close:
            close()


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Run one bounded FAQ collection/preprocessing cycle")
    parser.add_argument("--fixture", type=Path)
    parser.add_argument("--sink", choices=("json", "mongo"), default="json")
    parser.add_argument("--output-dir", type=Path)
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
                    "faq_state_path": args.output_dir / "faq_checkpoint.json",
                }
            )
        print(
            json.dumps(
                run_once(settings=settings, fixture=args.fixture, sink_name=args.sink, dry_run=args.dry_run),
                ensure_ascii=False,
            )
        )
        return 0
    except (FaqError, FaqPreprocessError, RuntimeError, ValueError) as exc:
        print(json.dumps({"status": "FAILED", "error_code": getattr(exc, "code", "faq_error")}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
