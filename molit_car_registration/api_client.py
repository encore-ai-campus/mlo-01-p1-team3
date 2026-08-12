"""국토교통부 통계누리 공식 Open API 클라이언트."""

from __future__ import annotations

import json
import re
import ssl
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .config import FORM_ID, OPEN_API_URL, STYLE_NUM
from .periods import month_label, normalize_month


class MolitOpenApiError(RuntimeError):
    """통계누리 Open API 호출 또는 응답 오류."""


def _find_value(payload: Any, names: set[str]) -> Any:
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
    """응답 내부의 date/data/items 배열을 찾아 행 목록으로 반환합니다."""
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


class MolitOpenApiClient:
    """월별 통계누리 Open API 요청을 담당합니다."""

    def __init__(self, api_key: str, insecure: bool = False, timeout: int = 60):
        if not api_key.strip():
            raise ValueError("MOLIT_API_KEY가 비어 있습니다.")
        self.api_key = api_key.strip()
        self.insecure = insecure
        self.timeout = timeout

    def fetch_period(self, period: str) -> list[dict[str, Any]]:
        period = normalize_month(period)
        params = {
            "key": self.api_key,
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
        context = (
            ssl._create_unverified_context()
            if self.insecure
            else ssl.create_default_context()
        )

        try:
            with urlopen(request, timeout=self.timeout, context=context) as response:
                raw_body = response.read()
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            # 통계누리는 아직 공개되지 않은 미래 월을 INFO-200이 아닌
            # HTTP 500으로 반환하는 경우가 있어 자료 없음으로 처리합니다.
            if exc.code == 500:
                if "INFO-100" in body or "인증키" in body:
                    raise MolitOpenApiError("MOLIT_API_KEY가 유효하지 않습니다.") from exc
                return []
            raise MolitOpenApiError(
                f"통계누리 Open API HTTP 오류({exc.code}, {period}): {body[:300]}"
            ) from exc
        except Exception as exc:
            raise MolitOpenApiError(f"통계누리 Open API 호출 실패({period}): {exc}") from exc

        try:
            payload = json.loads(raw_body.decode("utf-8-sig"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            preview = raw_body[:300].decode("utf-8", errors="replace")
            raise MolitOpenApiError(
                f"Open API 응답이 JSON이 아닙니다: {preview}"
            ) from exc

        status = _status_code(payload)
        message = _message(payload)
        if status not in {None, "INFO-000"}:
            if status == "INFO-200":
                return []
            if status == "INFO-100":
                raise MolitOpenApiError("MOLIT_API_KEY가 유효하지 않습니다.")
            if status == "INFO-300":
                raise MolitOpenApiError("해당 통계표 Open API 서비스가 개방 취소 상태입니다.")
            raise MolitOpenApiError(f"통계누리 Open API 오류 {status}: {message}")

        records = _find_record_list(payload)
        return [_normalize_row(record, period) for record in records]
