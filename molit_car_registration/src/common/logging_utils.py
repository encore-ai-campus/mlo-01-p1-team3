"""비밀값을 숨기는 구조화 JSONL 로그."""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Optional


SECRET_KEYS = {"api_key", "password", "secret", "token", "authorization"}
SECRET_PATTERN = re.compile(r"(?i)(api[_-]?key|password|token|secret)\s*[=:]\s*([^\s,;&]+)")


def redact(value: Any, key: str = "") -> Any:
    normalized = key.lower().replace("-", "_")
    if normalized in SECRET_KEYS or normalized.endswith(("_api_key", "_password")):
        return "[REDACTED]"
    if isinstance(value, Mapping):
        return {str(k): redact(v, str(k)) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact(item) for item in value]
    if isinstance(value, str):
        return SECRET_PATTERN.sub(r"\1=[REDACTED]", value)
    return value


class JsonlLogger:
    def __init__(self, path: Path, base_context: Optional[Mapping[str, Any]] = None):
        self.path = path
        self.base_context = dict(base_context or {})
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def event(self, level: str, event_name: str, message: str, **fields: Any) -> dict[str, Any]:
        record = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": level,
            "event_name": event_name,
            "message": message,
            **self.base_context,
            **fields,
        }
        safe = redact(record)
        line = json.dumps(safe, ensure_ascii=False, sort_keys=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
        print(line, file=sys.stderr)
        return safe
