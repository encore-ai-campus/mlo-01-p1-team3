"""비밀값을 가린 구조화 JSONL 로그 도구."""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Mapping, Optional


SECRET_KEYS = {"api_key", "authorization", "cookie", "password", "secret", "token", "uri", "webhook"}
SECRET_VALUE_PATTERN = re.compile(r"(?i)(api[_-]?key|authorization|password|token|secret)\s*[=:]\s*([^\s,;&]+)")
BEARER_TOKEN_PATTERN = re.compile(r"(?i)(authorization\s*[=:]\s*bearer\s+)[^\s,;&]+")
MONGODB_URI_PATTERN = re.compile(r"(?i)mongodb(?:\+srv)?://[^\s,;&]+")
WEBHOOK_URL_PATTERN = re.compile(r"(?i)https?://(?:(?:discord(?:app)?\.com/api/webhooks)|(?:hooks\.slack\.com))[^\s,;&]+")


def redact(value: Any, key: str = "") -> Any:
    """Return a copy of a log value with credentials and endpoint secrets removed."""
    normalized = key.lower().replace("-", "_")
    if normalized in SECRET_KEYS or normalized.endswith(("_api_key", "_password", "_secret", "_token")):
        return "[REDACTED]"
    if isinstance(value, Mapping):
        return {str(name): redact(item, str(name)) for name, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact(item) for item in value]
    if isinstance(value, str):
        safe = BEARER_TOKEN_PATTERN.sub(r"\1[REDACTED]", value)
        safe = SECRET_VALUE_PATTERN.sub(r"\1=[REDACTED]", safe)
        safe = MONGODB_URI_PATTERN.sub("[REDACTED]", safe)
        return WEBHOOK_URL_PATTERN.sub("[REDACTED]", safe)
    return value


class JsonlLogger:
    """Write one sanitized structured event per line and mirror it to stderr."""

    def __init__(self, path: Path, base_context: Optional[Mapping[str, Any]] = None) -> None:
        self.path = path
        self.base_context: Dict[str, Any] = dict(base_context or {})
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def event(self, level: str, event_name: str, message: str, **fields: Any) -> Dict[str, Any]:
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


__all__ = ["JsonlLogger", "redact"]
