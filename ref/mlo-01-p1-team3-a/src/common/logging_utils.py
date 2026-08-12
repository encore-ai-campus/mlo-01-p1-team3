"""Small JSONL logger with secret redaction for local and server runs."""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional


SECRET_KEY_PARTS = (
    "api_key",
    "authorization",
    "password",
    "secret",
    "token",
    "webhook",
    "cookie",
)
SECRET_VALUE_PATTERN = re.compile(
    r"(?i)(x-api-key|authorization|api[_-]?key|password|token|secret|webhook|mongodb_uri|sql_password)"
    r"\s*[=:]\s*([^\s,;&]+)"
)


def _looks_secret(key: str) -> bool:
    lowered = key.lower().replace("-", "_")
    if lowered in SECRET_KEY_PARTS:
        return True
    return lowered.endswith(("_api_key", "_password", "_secret", "_token", "_webhook", "_uri"))


def redact(value: Any, key: str = "") -> Any:
    if _looks_secret(key):
        return "[REDACTED]"
    if isinstance(value, Mapping):
        return {str(k): redact(v, str(k)) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact(item) for item in value]
    if isinstance(value, str):
        return SECRET_VALUE_PATTERN.sub(r"\1=[REDACTED]", value)
    return value


class JsonlLogger:
    """Write one sanitized structured event per line and mirror it to stderr."""

    def __init__(self, path: Path, base_context: Optional[Mapping[str, Any]] = None) -> None:
        self.path = path
        self.base_context: Dict[str, Any] = dict(base_context or {})
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def event(
        self,
        level: str,
        event_name: str,
        message: str,
        **fields: Any,
    ) -> Dict[str, Any]:
        record: Dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": level,
            "event_name": event_name,
            "message": message,
            **self.base_context,
            **fields,
        }
        safe_record = redact(record)
        line = json.dumps(safe_record, ensure_ascii=False, sort_keys=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
        print(line, file=sys.stderr)
        return safe_record
