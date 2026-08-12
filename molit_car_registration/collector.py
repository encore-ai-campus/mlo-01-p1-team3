"""최신 월 탐색과 누적 적재를 조정하는 모듈."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from .api_client import MolitOpenApiClient
from .config import FORM_ID, SOURCE_PAGE, STYLE_NUM, CollectorConfig
from .periods import add_month, current_period, month_distance, month_label
from .storage import build_headers, load_store, merge_rows, period_number, write_store


class DailyCollector:
    """Open API 클라이언트와 누적 저장소를 연결합니다."""

    def __init__(self, config: CollectorConfig):
        self.config = config
        self.client = MolitOpenApiClient(config.api_key, config.insecure)
        self.store_path = config.output_dir / config.store_name
        self.state_path = config.output_dir / config.state_name

    def find_latest_period(
        self, start_period: str
    ) -> tuple[str, list[dict[str, Any]], list[str]]:
        checked: list[str] = []
        for offset in range(self.config.max_lookback + 1):
            period = add_month(start_period, -offset)
            rows = self.client.fetch_period(period)
            checked.append(period)
            if rows:
                return period, rows, checked
        raise RuntimeError(
            f"최근 {self.config.max_lookback + 1}개월 동안 통계 자료를 찾지 못했습니다. "
            "form_id/style_num 또는 Open API 제공 상태를 확인하세요."
        )

    def _collect_incoming(
        self,
        existing: list[dict[str, str]],
        latest_period: str,
        latest_rows: list[dict[str, Any]],
    ) -> tuple[str, list[dict[str, Any]], list[str]]:
        if not existing:
            return "initial_latest", latest_rows, [latest_period]

        stored_periods = [period_number(row) for row in existing]
        stored_max = max(stored_periods)
        stored_min = min(stored_periods)
        latest_number = int(latest_period)

        if latest_number > stored_max:
            incoming: list[dict[str, Any]] = []
            fetched_periods: list[str] = []
            distance = month_distance(str(stored_max), latest_period)
            for offset in range(1, distance + 1):
                period = add_month(str(stored_max), offset)
                rows = latest_rows if period == latest_period else self.client.fetch_period(period)
                if rows:
                    incoming.extend(rows)
                    fetched_periods.append(period)
            return "append_new_latest", incoming, fetched_periods

        incoming = []
        fetched_periods = []
        if latest_number == stored_max:
            incoming.extend(latest_rows)
            fetched_periods.append(latest_period)

        previous_period = add_month(str(stored_min), -1)
        previous_rows = self.client.fetch_period(previous_period)
        if previous_rows:
            incoming.extend(previous_rows)
            fetched_periods.append(previous_period)
        return "backfill_previous", incoming, fetched_periods

    def run(self) -> tuple[Path, Path]:
        self.config.output_dir.mkdir(parents=True, exist_ok=True)
        existing, existing_headers = load_store(self.store_path)
        latest_period, latest_rows, checked_periods = self.find_latest_period(current_period())
        action, incoming, fetched_periods = self._collect_incoming(
            existing, latest_period, latest_rows
        )

        headers = build_headers(existing, incoming, existing_headers)
        merged = merge_rows(existing, incoming, headers)
        write_store(self.store_path, merged, headers)

        periods = [period_number(row) for row in merged if period_number(row) >= 0]
        state = {
            "source_page": SOURCE_PAGE,
            "form_id": FORM_ID,
            "style_num": STYLE_NUM,
            "action": action,
            "checked_for_latest": [month_label(period) for period in checked_periods],
            "fetched_periods": [month_label(period) for period in fetched_periods],
            "row_count": len(merged),
            "min_period": month_label(str(min(periods))) if periods else None,
            "max_period": month_label(str(max(periods))) if periods else None,
            "retrieved_at": datetime.now().astimezone().isoformat(),
            "insecure_tls_used": self.config.insecure,
            "column_count": len(headers),
            "api_key_source": "MOLIT_API_KEY environment variable",
        }
        self.state_path.write_text(
            json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return self.store_path, self.state_path


def run(
    output_dir: Path,
    api_key: str,
    insecure: bool = False,
    max_lookback: int = 24,
) -> tuple[Path, Path]:
    config = CollectorConfig(
        api_key=api_key,
        output_dir=output_dir,
        insecure=insecure,
        max_lookback=max_lookback,
    )
    return DailyCollector(config).run()
