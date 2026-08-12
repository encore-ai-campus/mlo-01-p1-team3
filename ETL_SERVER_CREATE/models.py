"""파이프라인에서 공유하는 실행 결과 모델이다."""

from dataclasses import dataclass, field
from typing import Any


# ============================================================================
# MODELS START: 수집·검증·적재 결과를 일관되게 표현한다.
# ============================================================================


@dataclass
class LoadStats:
    """한 저장소에 적재한 결과 건수다."""

    inserted: int = 0
    updated: int = 0
    unchanged: int = 0
    failed: int = 0


@dataclass
class PipelineResult:
    """한 source의 전체 실행 결과와 마지막 증분 체크포인트를 담는다."""

    source_name: str
    raw_count: int = 0
    valid_count: int = 0
    rejected_count: int = 0
    load_stats: LoadStats = field(default_factory=LoadStats)
    last_seq: int | None = None
    error_message: str | None = None


@dataclass
class RejectedRecord:
    """검증을 통과하지 못한 원본 데이터와 사유다."""

    source_name: str
    reason: str
    payload: dict[str, Any]


# ============================================================================
# MODELS END: 결과 모델 정의의 끝.
# ============================================================================
