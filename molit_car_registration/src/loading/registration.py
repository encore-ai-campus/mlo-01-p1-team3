"""전처리 결과를 저장하고 실행 상태를 관리합니다."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping, Sequence
from zoneinfo import ZoneInfo

from common.config import Settings


@dataclass(frozen=True)
class LoadStats:
    inserted_count: int = 0
    updated_count: int = 0
    unchanged_count: int = 0


class StateStore:
    def __init__(self, path: Path):
        self.path = path

    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {}
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError("registration checkpoint is unreadable") from exc
        if not isinstance(value, dict):
            raise RuntimeError("registration checkpoint must be an object")
        return value

    def save(self, value: Mapping[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(dict(value), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


class JsonQuotaLedger:
    def __init__(self, state: StateStore, limit: int, time_zone: str):
        self.state = state
        self.limit = limit
        self.time_zone = time_zone
        self.data = state.load()
        today = datetime.now(ZoneInfo(time_zone)).date().isoformat()
        if self.data.get("quota_date") != today:
            self.data.update({"quota_date": today, "used_count": 0, "quota_limit": limit})
            self.state.save(self.data)

    @property
    def used_count(self) -> int:
        return int(self.data.get("used_count", 0))

    @property
    def remaining(self) -> int:
        return max(0, self.limit - self.used_count)

    def reserve(self) -> None:
        if self.remaining <= 0:
            raise RuntimeError("daily registration API quota is exhausted")
        self.data["used_count"] = self.used_count + 1
        self.state.save(self.data)


class JsonlRegistrationSink:
    def __init__(self, path: Path):
        self.path = path

    @staticmethod
    def _key(row: Mapping[str, Any]) -> str:
        return "|".join(str(row.get(key) or "") for key in ("report_month", "sido_name", "sigungu_name", "vehicle_type", "usage_type"))

    def _read(self) -> dict[str, dict[str, Any]]:
        if not self.path.exists():
            return {}
        rows = {}
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                rows[self._key(row)] = row
        return rows

    def save(self, rows: Sequence[Mapping[str, Any]]) -> LoadStats:
        existing = self._read()
        inserted = updated = unchanged = 0
        for row in rows:
            key = self._key(row)
            old = existing.get(key)
            if old is None:
                inserted += 1
            elif old.get("content_hash") == row.get("content_hash"):
                unchanged += 1
            else:
                updated += 1
            existing[key] = dict(row)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in sorted(existing.values(), key=self._key)),
            encoding="utf-8",
        )
        return LoadStats(inserted, updated, unchanged)


def sink_for(settings: Settings, name: str) -> JsonlRegistrationSink:
    if name != "json":
        raise ValueError("this standalone folder currently supports --sink json; SQL adapter belongs to the team loading layer")
    return JsonlRegistrationSink(settings.output_dir / "vehicle_registration_reports.jsonl")
