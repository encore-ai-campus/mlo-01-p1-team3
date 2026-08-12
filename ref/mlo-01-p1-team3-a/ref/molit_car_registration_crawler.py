"""국토교통부 자동차등록현황보고 월별 수집기.

기본 대상은 사용자가 지정한 통계표(hFormId=5498)이며, 화면을 긁는 대신
공식 통계표가 사용하는 JSON API에서 월별 자료를 받아 CSV와 메타데이터로 저장합니다.

예시:
    python molit_car_registration_crawler.py --month 2026-06 --output-dir outputs --insecure
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import ssl
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen


BASE_URL = "https://stat.molit.go.kr"
SOURCE_PAGE = (
    f"{BASE_URL}/portal/cate/statView.do?hRsId=58&hFormId=5498"
)
FORM_ID = 5498
STYLE_NUM = 2


def api_get(path: str, params: dict[str, str], insecure: bool) -> dict[str, Any]:
    """국토교통부 통계 API의 JSON 응답을 반환합니다."""
    url = f"{BASE_URL}{path}?{urlencode(params)}"
    request = Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; MOLIT-stat-crawler/1.0)",
            "Referer": SOURCE_PAGE,
            "Accept": "application/json, text/plain, */*",
        },
    )
    context = ssl._create_unverified_context() if insecure else ssl.create_default_context()
    with urlopen(request, timeout=60, context=context) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not payload.get("result"):
        raise RuntimeError(f"통계 API가 실패를 반환했습니다: {payload}")
    return payload


def normalize_month(raw: str) -> tuple[str, str]:
    compact = re.sub(r"[^0-9]", "", raw)
    if len(compact) != 6:
        raise ValueError("월은 YYYY-MM 형식으로 입력해야 합니다. 예: 2026-06")
    year, month = compact[:4], compact[4:]
    if not 1 <= int(month) <= 12:
        raise ValueError("월은 01부터 12 사이여야 합니다.")
    return f"{year}-{month}", compact


def as_value(value: Any) -> Any:
    if value is None or value == "":
        return None
    if isinstance(value, str) and value.strip() in {"-", "–"}:
        return "-"
    if isinstance(value, str) and re.fullmatch(r"-?\d+", value.strip()):
        return int(value)
    return value


def build_columns(column_defs: list[dict[str, Any]]) -> tuple[list[str], list[str]]:
    """API 컬럼 정의를 사람이 읽기 쉬운 CSV 컬럼명으로 변환합니다."""
    direct = [c for c in column_defs if c["DIV_LV"] == 1]
    parents = {c["DATA_DIV_ID"]: c["DATA_DIV_NM"] for c in direct}
    data_columns = ["월", "시도명", "시군구"]
    column_ids = ["0", "1", "2"]
    for col in column_defs:
        if col["DIV_LV"] != 2:
            continue
        parent = parents.get(col["UP_DATA_DIV_ID"], "분류")
        data_columns.append(f"{parent}_{col['DATA_DIV_NM']}")
        column_ids.append(str(col["DATA_DIV_ID"]))
    return data_columns, column_ids


def crawl(month: str, output_dir: Path, insecure: bool) -> tuple[Path, Path, Path]:
    month_label, compact = normalize_month(month)
    output_dir.mkdir(parents=True, exist_ok=True)

    columns_response = api_get(
        "/portal/stat/columns.do",
        {"formId": str(FORM_ID), "styleNum": str(STYLE_NUM)},
        insecure,
    )
    column_defs = columns_response["data"]
    headers, column_ids = build_columns(column_defs)

    data_response = api_get(
        "/portal/stat/data.do",
        {
            "formId": str(FORM_ID),
            "styleNum": str(STYLE_NUM),
            "apprYn": "Y",
            "startDate": compact,
            "endDate": compact,
        },
        insecure,
    )
    rows = data_response["data"]
    table_rows = [[as_value(row.get(column_id)) for column_id in column_ids] for row in rows]

    csv_path = output_dir / f"자동차등록현황_{month_label}.csv"
    with csv_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(headers)
        writer.writerows(table_rows)

    columns_path = output_dir / f"자동차등록현황_{month_label}_컬럼정보.json"
    columns_path.write_text(
        json.dumps(column_defs, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    metadata = {
        "source_page": SOURCE_PAGE,
        "data_api": f"{BASE_URL}/portal/stat/data.do",
        "columns_api": f"{BASE_URL}/portal/stat/columns.do",
        "form_id": FORM_ID,
        "style_num": STYLE_NUM,
        "month": month_label,
        "row_count": len(table_rows),
        "column_count": len(headers),
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
        "insecure_tls_used": insecure,
        "notes": [
            "공식 통계표의 JSON API 응답을 수집한 원자료입니다.",
            "숫자형 값은 숫자로 저장하고, API의 '-' 표시는 그대로 보존합니다.",
        ],
    }
    metadata_path = output_dir / f"자동차등록현황_{month_label}_메타데이터.json"
    metadata_path.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    return csv_path, columns_path, metadata_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--month", default="2026-06", help="수집 월: YYYY-MM")
    parser.add_argument("--output-dir", default="outputs", help="결과 저장 폴더")
    parser.add_argument(
        "--insecure",
        action="store_true",
        help="인증서 검증을 끕니다. 현재 통계 사이트 인증서 오류가 있을 때만 사용하세요.",
    )
    args = parser.parse_args()
    try:
        paths = crawl(args.month, Path(args.output_dir), args.insecure)
    except Exception as exc:  # pragma: no cover - command-line error path
        print(f"수집 실패: {exc}", file=sys.stderr)
        return 1
    for path in paths:
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
