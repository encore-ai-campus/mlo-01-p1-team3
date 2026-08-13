"""Stable contracts shared at stage boundaries.

The stage packages exchange ordinary mappings inside immutable envelopes. A
collector can change its retry, pagination, or transport implementation
without requiring a preprocessing change as long as these boundary fields
remain stable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Mapping, Optional, Sequence, Tuple

RawRecord = Mapping[str, Any]
PreparedRecord = Mapping[str, Any]


@dataclass(frozen=True)
class CollectionEnvelope:
    """A collection result passed from a Source adapter to preprocessing."""

    source_name: str
    collected_at: datetime
    records: Tuple[RawRecord, ...]
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RejectedRecord:
    """A record-level validation failure without raw payload logging."""

    index: int
    error_code: str
    stable_key: Optional[str] = None


@dataclass(frozen=True)
class PreparedBatch:
    """Validated records and reject summaries handed to a loader."""

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
    started_at: datetime
    schedule_name: Optional[str] = None


def as_tuple(records: Sequence[Mapping[str, Any]]) -> Tuple[Mapping[str, Any], ...]:
    """Freeze a stage boundary without deep-copying source-owned mappings."""

    return tuple(records)
