"""cars와 FAQ 데이터의 적재 전 필수값을 검증한다."""

from typing import Any

from models import RejectedRecord


# ============================================================================
# VALIDATORS START: 레코드를 valid와 rejected로 안전하게 분리한다.
# ============================================================================


def validate_cars(records: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[RejectedRecord]]:
    """차량 원본에서 필수 id/listingNumber가 없는 레코드를 거절한다."""
    valid, rejected = [], []
    for record in records:
        payload = record.get("payload", record)
        if not isinstance(payload, dict):
            rejected.append(RejectedRecord("cars", "payload is not an object", {"value": payload}))
        elif payload.get("id") is None:
            rejected.append(RejectedRecord("cars", "missing required field: id", payload))
        elif not payload.get("listingNumber"):
            rejected.append(RejectedRecord("cars", "missing required field: listingNumber", payload))
        else:
            valid.append(payload)
    return valid, rejected


def validate_faqs(records: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[RejectedRecord]]:
    """FAQ의 faq_id/question/answer 필수값을 검증한다."""
    valid, rejected = [], []
    for record in records:
        missing = [key for key in ("faq_id", "question", "answer") if not record.get(key)]
        if missing:
            rejected.append(RejectedRecord("faqs", f"missing required field: {', '.join(missing)}", record))
        else:
            valid.append(record)
    return valid, rejected


# ============================================================================
# VALIDATORS END: 데이터 검증 기능의 끝.
# ============================================================================
