"""
===============================================================================
[TEST START] common.logging_utils unit tests

Purpose:
    Verify the logger implementation now lives in common.logging_utils,
    nested secrets are masked, JSONL is written, and stderr is mirrored.
===============================================================================
"""

from __future__ import annotations

import contextlib
import io
import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for import_path in (str(ROOT), str(SRC)):
    if import_path not in sys.path:
        sys.path.insert(0, import_path)

from common.logging_utils import JsonlLogger, redact  # noqa: E402
from src.logging.logging_utils import (  # noqa: E402
    JsonlLogger as CompatibilityLogger,
    redact as compatibility_redact,
)


def test_common_logging_utils_masks_secrets_and_writes_jsonl() -> None:
    """Check compatibility exports, nested redaction, file output, and stderr."""

    assert CompatibilityLogger is JsonlLogger
    assert compatibility_redact is redact
    assert redact(
        {
            "api_key": "secret-api",
            "password": "secret-password",
            "nested": {"uri": "mongodb://user:secret@host/db"},
        }
    ) == {
        "api_key": "[REDACTED]",
        "password": "[REDACTED]",
        "nested": {"uri": "[REDACTED]"},
    }

    with TemporaryDirectory() as temporary_directory:
        log_path = Path(temporary_directory) / "events.jsonl"
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            returned = JsonlLogger(log_path).event(
                "INFO", "unit_test", "ok", api_key="secret-api", count=1
            )

        record = json.loads(log_path.read_text(encoding="utf-8"))
        assert record == returned
        assert record["api_key"] == "[REDACTED]"
        assert record["count"] == 1
        assert json.loads(stderr.getvalue())["event_name"] == "unit_test"


"""
===============================================================================
[TEST END] common.logging_utils unit tests
===============================================================================
"""
