"""Pure FAQ raw-record to MongoDB document transformation."""

from __future__ import annotations

import hashlib
import html
import json
import re
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

from common.config import Settings
from common.time_utils import format_utc_date, format_utc_datetime


class FaqPreprocessError(ValueError):
    """A FAQ card cannot satisfy the MongoDB document contract."""

    def __init__(self, message: str, code: str = "faq_rejected") -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class FaqRejectedRecord:
    index: int
    error_code: str
    faq_id: Optional[str]


def normalize_text(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = html.unescape(str(value))
    text = re.sub(r"[\x00-\x1f\x7f]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text or None


def normalize_url(value: Any) -> Optional[str]:
    from urllib.parse import urlsplit, urlunsplit

    text = normalize_text(value)
    if not text:
        return None
    parsed = urlsplit(text)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    return urlunsplit(parsed._replace(fragment=""))


def _iso_date(value: Any) -> Optional[str]:
    text = normalize_text(value)
    if not text:
        return None
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        normalized = text
    elif re.fullmatch(r"\d{8}", text):
        normalized = f"{text[:4]}-{text[4:6]}-{text[6:]}"
    else:
        raise FaqPreprocessError(
            "reviewed_at must be YYYY-MM-DD or YYYYMMDD", code="invalid_reviewed_at"
        )
    try:
        canonical_date = format_utc_date(normalized, required=True)
        canonical_datetime = format_utc_datetime(canonical_date, required=True)
    except (TypeError, ValueError) as exc:
        raise FaqPreprocessError("reviewed_at is not a calendar date", code="invalid_reviewed_at") from exc
    assert canonical_datetime is not None
    return canonical_datetime


def _canonical_hash(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def transform_faq_record(
    record: Mapping[str, Any], *, settings: Settings, run_id: str, collected_at: str
) -> Dict[str, Any]:
    try:
        normalized_collected_at = format_utc_datetime(collected_at, required=True)
    except (TypeError, ValueError) as exc:
        raise FaqPreprocessError("collected_at must be ISO 8601", code="invalid_collected_at") from exc
    assert normalized_collected_at is not None

    faq_id = normalize_text(record.get("faq_id"))
    question = normalize_text(record.get("question"))
    answer = normalize_text(record.get("answer"))
    brand = normalize_text(record.get("brand"))
    category = normalize_text(record.get("category"))
    source_url = normalize_url(record.get("source_url"))
    if not question:
        raise FaqPreprocessError("question is required", code="missing_question")
    if not answer:
        raise FaqPreprocessError("answer is required", code="missing_answer")
    if not brand:
        raise FaqPreprocessError("brand is required", code="missing_brand")
    if not category:
        raise FaqPreprocessError("category is required", code="missing_category")
    if not source_url:
        raise FaqPreprocessError("source_url must be an absolute URL", code="invalid_source_url")
    if not faq_id:
        faq_id = hashlib.sha256(f"{source_url}\n{question}".encode("utf-8")).hexdigest()
    source_updated_at = _iso_date(record.get("reviewed_at"))
    if not source_updated_at:
        raise FaqPreprocessError("reviewed_at is required", code="missing_reviewed_at")
    license_name = normalize_text(record.get("license")) or normalize_text(settings.faq_license)
    attribution = normalize_text(record.get("attribution")) or normalize_text(settings.faq_attribution)
    if not license_name:
        raise FaqPreprocessError("license policy is required", code="missing_license")
    if not attribution:
        raise FaqPreprocessError("attribution is required", code="missing_attribution")

    stable = {
        "faq_id": faq_id,
        "question": question,
        "answer": answer,
        "brand": brand,
        "category": category,
        "source_url": source_url,
        "source_updated_at": source_updated_at,
        "license": license_name,
        "attribution": attribution,
    }
    return {
        **stable,
        "run_id": run_id,
        "collected_at": normalized_collected_at,
        "content_hash": _canonical_hash(stable),
        "is_active": True,
        "created_at": normalized_collected_at,
        "updated_at": normalized_collected_at,
    }


def transform_faq_records(
    records: Iterable[Mapping[str, Any]], *, settings: Settings, run_id: str, collected_at: str
) -> Tuple[List[Dict[str, Any]], List[FaqRejectedRecord]]:
    valid: List[Dict[str, Any]] = []
    rejected: List[FaqRejectedRecord] = []
    for index, record in enumerate(records):
        try:
            valid.append(transform_faq_record(record, settings=settings, run_id=run_id, collected_at=collected_at))
        except FaqPreprocessError as exc:
            rejected.append(
                FaqRejectedRecord(index=index, error_code=exc.code, faq_id=normalize_text(record.get("faq_id")))
            )
    return valid, rejected
