"""단계 사이에서 공유하는 안정적인 데이터 계약."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Mapping, Optional, Tuple


@dataclass(frozen=True)
class CollectionEnvelope:
    source_name: str
    collected_at: datetime
    records: Tuple[Mapping[str, Any], ...]
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RejectedRecord:
    index: int
    error_code: str
    stable_key: Optional[str] = None


@dataclass(frozen=True)
class PreparedBatch:
    records: Tuple[Mapping[str, Any], ...]
    rejected: Tuple[RejectedRecord, ...] = ()
