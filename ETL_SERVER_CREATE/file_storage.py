"""Raw 원본과 rejected 데이터를 파일로 안전하게 보관한다."""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config import Settings
from models import RejectedRecord


# ============================================================================
# FILE STORAGE START: 실행 시점별 JSON 감사 파일을 저장한다.
# ============================================================================


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _write_json(path: Path, contents: Any) -> Path:
    """상위 경로를 만들고 UTF-8 JSON을 원자적으로 기록한다."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(path.suffix + ".tmp")
    with temporary_path.open("w", encoding="utf-8") as file:
        json.dump(contents, file, ensure_ascii=False, indent=2, default=str)
    temporary_path.replace(path)
    return path


def save_raw(settings: Settings, source_name: str, records: list[dict[str, Any]]) -> Path:
    """변환 전 원본 응답을 날짜별 raw 디렉터리에 저장한다."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return _write_json(settings.raw_dir / today / f"{source_name}_{_timestamp()}.json", records)


def save_rejected(settings: Settings, source_name: str, records: list[RejectedRecord]) -> Path | None:
    """검증 실패 원본과 사유를 날짜별 rejected 디렉터리에 저장한다."""
    if not records:
        return None
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    contents = [{"source_name": record.source_name, "reason": record.reason, "payload": record.payload} for record in records]
    return _write_json(settings.rejected_dir / today / f"{source_name}_{_timestamp()}.json", contents)


# ============================================================================
# FILE STORAGE END: 원본·실패 데이터 보관 기능의 끝.
# ============================================================================
