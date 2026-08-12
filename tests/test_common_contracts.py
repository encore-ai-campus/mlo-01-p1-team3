"""
===============================================================================
[TEST START] common.contracts unit tests

Purpose:
    Verify immutable stage-boundary contracts and the reference RunContext
    constructor order/default schedule contract.
===============================================================================
"""

from __future__ import annotations

import sys
from dataclasses import fields
from datetime import datetime, timezone
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for import_path in (str(ROOT), str(SRC)):
    if import_path not in sys.path:
        sys.path.insert(0, import_path)

from common.contracts import (  # noqa: E402
    CollectionEnvelope,
    LoadStats,
    PreparedBatch,
    RejectedRecord,
    RunContext,
    as_tuple,
)


def test_common_contracts_are_immutable_and_reference_compatible() -> None:
    """Check frozen contracts, boundary tuples, and reference RunContext."""

    started_at = datetime.now(timezone.utc)
    envelope = CollectionEnvelope("cars", started_at, ({"id": 1},))
    batch = PreparedBatch(({"id": 1},), (RejectedRecord(0, "invalid", "1"),))
    context = RunContext("run-1", "cars", started_at)
    scheduled = RunContext("run-2", "cars", started_at, schedule_name="daily")

    assert envelope.records == ({"id": 1},)
    assert batch.rejected[0].error_code == "invalid"
    assert context.schedule_name is None
    assert scheduled.schedule_name == "daily"
    assert [field.name for field in fields(RunContext)] == [
        "run_id",
        "pipeline_name",
        "started_at",
        "schedule_name",
    ]
    assert as_tuple([{"id": 1}]) == ({"id": 1},)
    assert LoadStats(1, 2, 3).updated_count == 2

    with pytest.raises((AttributeError, TypeError)):
        envelope.source_name = "changed"  # type: ignore[misc]


"""
===============================================================================
[TEST END] common.contracts unit tests
===============================================================================
"""
