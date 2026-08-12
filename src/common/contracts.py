"""Stable, database-neutral contracts shared at stage boundaries."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Mapping, Optional, Sequence, Tuple


RawRecord = Mapping[str, Any]
PreparedRecord = Mapping[str, Any]


@dataclass(frozen=True)
class CollectionEnvelope:
    """Source-shaped records handed from collection to preprocessing."""

    source_name: str
    collected_at: datetime
    records: Tuple[RawRecord, ...]
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RejectedRecord:
    """A record-level rejection summary without retaining source payloads."""

    index: int
    error_code: str
    stable_key: Optional[str] = None


@dataclass(frozen=True)
class PreparedBatch:
    """Valid prepared data and its reject summaries handed to loading."""

    records: Tuple[PreparedRecord, ...]
    rejected: Tuple[RejectedRecord, ...] = ()


@dataclass(frozen=True)
class LoadStats:
    inserted_count: int = 0
    updated_count: int = 0
    unchanged_count: int = 0


@dataclass(frozen=True)
class RunContext:
    run_id: str
    pipeline_name: str
    schedule_name: Optional[str]
    started_at: datetime


def as_tuple(records: Sequence[Mapping[str, Any]]) -> Tuple[Mapping[str, Any], ...]:
    """Freeze a stage boundary without changing the source-owned mappings."""

    return tuple(records)


__all__ = [
    "CollectionEnvelope",
    "LoadStats",
    "PreparedBatch",
    "PreparedRecord",
    "RawRecord",
    "RejectedRecord",
    "RunContext",
    "as_tuple",
]
