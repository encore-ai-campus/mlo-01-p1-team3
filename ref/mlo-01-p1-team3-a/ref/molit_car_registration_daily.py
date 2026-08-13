"""통계누리 공식 Open API 자동차등록대수현황 시도별 일일 적재기.

국토교통부 통계누리의 공식 REST Open API를 하루 한 번 호출해 누적 CSV를
관리합니다. 인증키는 코드에 저장하지 않고 MOLIT_API_KEY 환경변수에서 읽습니다.

동작 규칙:
  1. 새 월 자료가 있으면 누락된 월부터 최신 월까지 받아 최신 월이 위에 오도록 저장
  2. 새 월 자료가 없으면 기존 최저 월의 직전 월을 받아 누적 자료 아래쪽에 추가
  3. 같은 월·지역 행을 다시 받으면 기존 행을 최신 값으로 갱신

예시(PowerShell):
    $env:MOLIT_API_KEY = "발급받은_인증키"
    python molit_car_registration_daily.py --output-dir outputs

대상 통계표:
  - form_id: 5498
  - style_num: 2
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import ssl
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError


BASE_URL = "https://stat.molit.go.kr"
OPEN_API_URL = f"{BASE_URL}/portal/openapi/service/rest/getList.do"
SOURCE_PAGE = f"{BASE_URL}/portal/cate/statView.do?hRsId=58&hFormId=5498"
FORM_ID = 5498
STYLE_NUM = 2
DEFAULT_STORE_NAME = "자동차등록대수현황_시도별_누적.csv"
DEFAULT_STATE_NAME = "자동차등록대수현황_시도별_누적_상태.json"


def normalize_month(raw: str) -> str:
    compact = re.sub(r"[^0-9]", "", raw)
    if len(compact) != 6:
        raise ValueError("월은 YYYY-MM 또는 YYYYMM 형식이어야 합니다.")
    year, month = int(compact[:4]), int(compact[4:])
    if not 1 <= month <= 12:
        raise ValueError("월은 01부터 12 사이여야 합니다.")
    return f"{year:04d}{month:02d}"


def month_label(period: str) -> str:
    return f"{period[:4]}-{period[4:]}"


def add_month(period: str, offset: int) -> str:
    year, month = int(period[:4]), int(period[4:])
    serial = year * 12 + (month - 1) + offset
    new_year, zero_based_month = divmod(serial, 12)
    return f"{new_year:04d}{zero_based_month + 1:02d}"


def month_distance(start_period: str, end_period: str) -> int:
    start_year, start_month = int(start_period[:4]), int(start_period[4:])
    end_year, end_month = int(end_period[:4]), int(end_period[4:])
    return (end_year * 12 + end_month) - (start_year * 12 + start_month)


def current_period() -> str:
    return datetime.now().strftime("%Y%m")


def _find_value(payload: Any, names: set[str]) -> Any:
    """중첩 JSON에서 지정된 이름의 첫 번째 값을 찾습니다."""
    if isinstance(payload, dict):
        for key, value in payload.items():
            if str(key).lower() in names:
                return value
        for value in payload.values():
            found = _find_value(value, names)
            if found is not None:
                return found
    elif isinstance(payload, list):
        for value in payload:
            found = _find_value(value, names)
            if found is not None:
                return found
    return None


def _find_record_list(payload: Any) -> list[dict[str, Any]]:
    """공식 API 응답의 date/data/items 배열을 응답 형식 변화에 맞춰 찾습니다."""
    if isinstance(payload, dict):
        priority = {"date", "data", "items", "item", "rows", "row"}
        for key, value in payload.items():
            if str(key).lower() in priority:
                records = _find_record_list(value)
                if records:
                    return records
        for value in payload.values():
            records = _find_record_list(value)
            if records:
                return records
        return []

    if isinstance(payload, list):
        dictionaries = [item for item in payload if isinstance(item, dict)]
        if dictionaries:
            return dictionaries
        for item in payload:
            records = _find_record_list(item)
            if records:
                return records
    return []


def _scalar_value(value: Any) -> Any:
    if value is None or value == "":
        return None
    if isinstance(value, str) and value.strip() in {"-", "–"}:
        return "-"
    if isinstance(value, str) and re.fullmatch(r"-?\d+", value.strip()):
        return int(value)
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return value


def _normalize_row(raw: dict[str, Any], period: str) -> dict[str, Any]:
    row: dict[str, Any] = {"기준월": month_label(period)}
    ignored = {
        "status_code",
        "statuscode",
        "message",
        "unitname",
        "formname",
        "date",
    }
    for index, (key, value) in enumerate(raw.items(), start=1):
        normalized_key = str(key).strip() or f"컬럼_{index}"
        if normalized_key.lower().replace("-", "_") in ignored:
            continue
        row[normalized_key] = _scalar_value(value)
    return row


def _status_code(payload: Any) -> str | None:
    value = _find_value(payload, {"status_code", "statuscode"})
    return str(value).strip() if value is not None else None


def _message(payload: Any) -> str:
    value = _find_value(payload, {"message", "resultmsg", "result_msg"})
    return str(value).strip() if value is not None else ""


def api_get(
    period: str,
    api_key: str,
    insecure: bool,
) -> list[dict[str, Any]]:
    params = {
        "key": api_key,
        "form_id": str(FORM_ID),
        "style_num": str(STYLE_NUM),
        "start_dt": period,
        "end_dt": period,
    }
    request = Request(
        f"{OPEN_API_URL}?{urlencode(params)}",
        headers={
            "User-Agent": "MOLIT-OpenAPI-car-registration/1.0",
            "Accept": "application/json, text/plain, */*",
        },
    )
    context = ssl._create_unverified_context() if insecure else ssl.create_default_context()
    try:
        with urlopen(request, timeout=60, context=context) as response:
            raw_body = response.read()
    except HTTPError as exc:
        # 통계누리는 아직 공개되지 않은 미래 월을 INFO-200이 아닌
        # HTTP 500으로 반환하는 경우가 있습니다. 최신 월 탐색에서는
        # 해당 월에 자료가 없는 것으로 간주하고 이전 월을 계속 확인합니다.
        body = exc.read().decode("utf-8", errors="replace")
        if exc.code == 500:
            if "INFO-100" in body or "인증키" in body:
                raise RuntimeError("MOLIT_API_KEY가 유효하지 않습니다.") from exc
            return []
        raise RuntimeError(
            f"통계누리 Open API HTTP 오류({exc.code}, {period}): {body[:300]}"
        ) from exc
    except Exception as exc:
        raise RuntimeError(f"통계누리 Open API 호출 실패({period}): {exc}") from exc

    try:
        payload = json.loads(raw_body.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        preview = raw_body[:300].decode("utf-8", errors="replace")
        raise RuntimeError(f"Open API 응답이 JSON이 아닙니다: {preview}") from exc

    status = _status_code(payload)
    message = _message(payload)
    if status not in {None, "INFO-000"}:
        if status == "INFO-200":
            return []
        if status == "INFO-100":
            raise RuntimeError("MOLIT_API_KEY가 유효하지 않습니다.")
        if status == "INFO-300":
            raise RuntimeError("해당 통계표 Open API 서비스가 개방 취소 상태입니다.")
        raise RuntimeError(f"통계누리 Open API 오류 {status}: {message}")

    records = _find_record_list(payload)
    return [_normalize_row(record, period) for record in records]


def find_latest_period(
    start_period: str,
    api_key: str,
    insecure: bool,
    max_lookback: int,
) -> tuple[str, list[dict[str, Any]], list[str]]:
    checked: list[str] = []
    for offset in range(max_lookback + 1):
        period = add_month(start_period, -offset)
        rows = api_get(period, api_key, insecure)
        checked.append(period)
        if rows:
            return period, rows, checked
    raise RuntimeError(
        f"최근 {max_lookback + 1}개월 동안 통계 자료를 찾지 못했습니다. "
        "form_id/style_num 또는 Open API 제공 상태를 확인하세요."
    )


def load_store(path: Path) -> tuple[list[dict[str, str]], list[str]]:
    if not path.exists():
        return [], []
    with path.open("r", newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        headers = reader.fieldnames or []
        return [dict(row) for row in reader], headers


def row_key(row: dict[str, Any], headers: list[str]) -> tuple[str, ...]:
    # 첫 세 컬럼은 기준월과 행 식별용 지역 컬럼으로 사용합니다.
    identity_headers = headers[:3]
    return tuple(
        "" if row.get(header) is None else str(row.get(header))
        for header in identity_headers
    )


def period_number(row: dict[str, Any]) -> int:
    raw = str(row.get("기준월", "")).replace("-", "")
    try:
        return int(normalize_month(raw))
    except ValueError:
        return -1


def build_headers(
    existing: list[dict[str, Any]],
    incoming: list[dict[str, Any]],
    existing_headers: list[str],
) -> list[str]:
    headers = list(existing_headers)
    if not headers:
        headers = ["기준월"]
    for row in [*existing, *incoming]:
        for key in row:
            if key not in headers:
                headers.append(key)
    if "기준월" in headers and headers[0] != "기준월":
        headers.remove("기준월")
        headers.insert(0, "기준월")
    return headers


def merge_rows(
    existing: list[dict[str, Any]],
    incoming: list[dict[str, Any]],
    headers: list[str],
) -> list[dict[str, Any]]:
    merged: dict[tuple[str, ...], dict[str, Any]] = {}
    for row in existing:
        merged[row_key(row, headers)] = {header: row.get(header, "") for header in headers}
    for row in incoming:
        merged[row_key(row, headers)] = {header: row.get(header, "") for header in headers}

    return sorted(
        merged.values(),
        key=lambda row: (-period_number(row), row_key(row, headers)),
    )


def write_store(path: Path, rows: list[dict[str, Any]], headers: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def run(
    output_dir: Path,
    api_key: str,
    insecure: bool,
    max_lookback: int,
    store_name: str = DEFAULT_STORE_NAME,
) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    store_path = output_dir / store_name
    state_path = output_dir / DEFAULT_STATE_NAME

    existing, existing_headers = load_store(store_path)
    latest_period, latest_rows, checked_periods = find_latest_period(
        current_period(), api_key, insecure, max_lookback
    )

    incoming: list[dict[str, Any]] = []
    fetched_periods: list[str] = []
    action: str

    if not existing:
        action = "initial_latest"
        incoming.extend(latest_rows)
        fetched_periods.append(latest_period)
    else:
        stored_periods = [period_number(row) for row in existing]
        stored_max = max(stored_periods)
        stored_min = min(stored_periods)
        latest_number = int(latest_period)

        if latest_number > stored_max:
            action = "append_new_latest"
            distance = month_distance(str(stored_max), latest_period)
            for offset in range(1, distance + 1):
                period = add_month(str(stored_max), offset)
                rows = latest_rows if period == latest_period else api_get(
                    period, api_key, insecure
                )
                if rows:
                    incoming.extend(rows)
                    fetched_periods.append(period)
        else:
            action = "backfill_previous"
            if latest_number == stored_max:
                incoming.extend(latest_rows)
                fetched_periods.append(latest_period)

            previous_period = add_month(str(stored_min), -1)
            previous_rows = api_get(previous_period, api_key, insecure)
            if previous_rows:
                incoming.extend(previous_rows)
                fetched_periods.append(previous_period)

    headers = build_headers(existing, incoming, existing_headers)
    merged = merge_rows(existing, incoming, headers)
    write_store(store_path, merged, headers)

    periods = [period_number(row) for row in merged if period_number(row) >= 0]
    state = {
        "source_page": SOURCE_PAGE,
        "open_api_url": OPEN_API_URL,
        "form_id": FORM_ID,
        "style_num": STYLE_NUM,
        "action": action,
        "checked_for_latest": [month_label(period) for period in checked_periods],
        "fetched_periods": [month_label(period) for period in fetched_periods],
        "row_count": len(merged),
        "min_period": month_label(str(min(periods))) if periods else None,
        "max_period": month_label(str(max(periods))) if periods else None,
        "retrieved_at": datetime.now().astimezone().isoformat(),
        "insecure_tls_used": insecure,
        "column_count": len(headers),
        "api_key_source": "MOLIT_API_KEY environment variable",
    }
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    return store_path, state_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", default="outputs", help="결과 저장 폴더")
    parser.add_argument(
        "--max-lookback",
        type=int,
        default=24,
        help="최신 월 검색 시 현재 월부터 거슬러 올라갈 최대 개월 수",
    )
    parser.add_argument(
        "--insecure",
        action="store_true",
        help="인증서 검증을 끕니다. TLS 오류가 있을 때만 사용하세요.",
    )
    args = parser.parse_args()
    if args.max_lookback < 0:
        parser.error("--max-lookback은 0 이상이어야 합니다.")

    api_key = os.environ.get("MOLIT_API_KEY", "").strip()
    if not api_key:
        print(
            "실행 실패: MOLIT_API_KEY 환경변수에 통계누리 Open API 인증키를 설정하세요.",
            file=sys.stderr,
        )
        return 2

    try:
        store_path, state_path = run(
            Path(args.output_dir), api_key, args.insecure, args.max_lookback
        )
    except Exception as exc:  # pragma: no cover - command-line error path
        print(f"통계누리 Open API 일일 적재 실패: {exc}", file=sys.stderr)
        return 1

    print(store_path)
    print(state_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
