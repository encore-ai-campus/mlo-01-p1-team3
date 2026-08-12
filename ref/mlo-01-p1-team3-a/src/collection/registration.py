"""Automobile-registration Source adapter and response-envelope parsing."""

from __future__ import annotations

import json
import re
import ssl
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from common.config import Settings


class RegistrationError(RuntimeError):
    """An upstream, response, or registration collection contract error."""

    def __init__(self, message: str, code: str = "registration_error", *, retryable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable


@dataclass(frozen=True)
class RegistrationPage:
    period: str
    records: List[Dict[str, Any]]
    response_sha256: str


def normalize_period(value: Any) -> str:
    text = re.sub(r"[^0-9]", "", str(value or ""))
    if len(text) != 6:
        raise RegistrationError("period must be YYYY-MM", code="invalid_reference_month")
    year, month = int(text[:4]), int(text[4:])
    if not 1 <= month <= 12:
        raise RegistrationError("period month is invalid", code="invalid_reference_month")
    return f"{year:04d}{month:02d}"


def month_label(period: str) -> str:
    return f"{period[:4]}-{period[4:]}"


def add_month(period: str, offset: int) -> str:
    year, month = int(period[:4]), int(period[4:])
    serial = year * 12 + (month - 1) + offset
    next_year, zero_month = divmod(serial, 12)
    return f"{next_year:04d}{zero_month + 1:02d}"


def current_period(time_zone: str = "Asia/Seoul") -> str:
    from zoneinfo import ZoneInfo

    return datetime.now(ZoneInfo(time_zone)).strftime("%Y%m")


def find_value(payload: Any, names: set[str]) -> Any:
    if isinstance(payload, dict):
        for key, value in payload.items():
            if str(key).lower().replace("-", "_") in names:
                return value
        for value in payload.values():
            found = find_value(value, names)
            if found is not None:
                return found
    elif isinstance(payload, list):
        for value in payload:
            found = find_value(value, names)
            if found is not None:
                return found
    return None


def extract_record_list(payload: Any) -> List[Dict[str, Any]]:
    """Find the item/row array in common MOLIT JSON envelopes."""

    if isinstance(payload, dict):
        priority = {"date", "data", "items", "item", "rows", "row", "result"}
        for key, value in payload.items():
            if str(key).lower() in priority:
                records = extract_record_list(value)
                if records:
                    return records
        for value in payload.values():
            records = extract_record_list(value)
            if records:
                return records
        return []
    if isinstance(payload, list):
        dictionaries = [item for item in payload if isinstance(item, dict)]
        if dictionaries:
            return dictionaries
        for item in payload:
            records = extract_record_list(item)
            if records:
                return records
    return []


class RegistrationApiClient:
    """MOLIT Open API client. The key is passed only as required by its contract."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        if not settings.registration_api_key:
            raise RegistrationError("REGISTRATION_API_KEY or MOLIT_API_KEY is required", code="missing_api_key")
        if urlsplit(settings.registration_api_url).netloc != "stat.molit.go.kr":
            raise RegistrationError("registration endpoint is outside the approved host", code="source_allowlist")

    def fetch_period(self, period: str, *, reserve_call: Callable[[], None]) -> Tuple[Any, bytes]:
        period = normalize_period(period)
        params = {
            "key": self.settings.registration_api_key,
            "form_id": str(self.settings.registration_form_id),
            "style_num": str(self.settings.registration_style_num),
            "start_dt": period,
            "end_dt": period,
        }
        url = f"{self.settings.registration_api_url}?{urlencode(params)}"
        for attempt in range(3):
            reserve_call()
            request = Request(
                url,
                headers={
                    "Accept": "application/json, text/plain, */*",
                    "User-Agent": self.settings.user_agent,
                    "Referer": self.settings.registration_source_page,
                },
                method="GET",
            )
            try:
                with urlopen(request, timeout=self.settings.timeout_seconds, context=ssl.create_default_context()) as response:
                    body = response.read(8 * 1024 * 1024 + 1)
                    if len(body) > 8 * 1024 * 1024:
                        raise RegistrationError("registration response exceeded 8 MiB", code="response_too_large")
            except HTTPError as exc:
                body = exc.read(512 * 1024)
                if exc.code == 500 and b"INFO-200" in body:
                    return {"data": []}, body
                if exc.code == 500 and (b"INFO-100" in body or "인증키".encode("utf-8") in body):
                    raise RegistrationError("registration API key is invalid", code="invalid_api_key") from exc
                if exc.code == 500 and b"INFO-300" in body:
                    raise RegistrationError("registration API service is unavailable", code="api_closed") from exc
                if exc.code not in {429, 500, 502, 503, 504} or attempt == 2:
                    raise RegistrationError(f"registration upstream HTTP {exc.code}", code=f"http_{exc.code}") from exc
                time.sleep(2.0**attempt)
                continue
            except (URLError, TimeoutError) as exc:
                if attempt == 2:
                    raise RegistrationError("registration upstream connection failed", code="connection_error") from exc
                time.sleep(2.0**attempt)
                continue
            try:
                payload = json.loads(body.decode("utf-8-sig"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise RegistrationError("registration response is not valid JSON", code="json_schema") from exc
            status = find_value(payload, {"status_code", "statuscode"})
            if status in {"INFO-100", 100}:
                raise RegistrationError("registration API key is invalid", code="invalid_api_key")
            if status == "INFO-300":
                raise RegistrationError("registration API service is unavailable", code="api_closed")
            if status not in {None, "", "INFO-000", 0, "0"} and status != "INFO-200":
                message = find_value(payload, {"message", "resultmsg", "result_msg"})
                raise RegistrationError(
                    f"registration API returned {status}: {message or 'unknown error'}", code="api_error"
                )
            return payload, body
        raise RegistrationError("registration retry loop exhausted", code="retry_exhausted")


class FixtureRegistrationClient:
    """Finite fixture client supporting one payload or period-keyed pages."""

    def __init__(self, path: Path) -> None:
        try:
            self.payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RegistrationError("registration fixture could not be read", code="fixture_error") from exc

    def fetch_period(self, period: str, *, reserve_call: Callable[[], None]) -> Tuple[Any, bytes]:
        reserve_call()
        payload = self.payload
        if isinstance(payload, dict) and isinstance(payload.get("pages"), list):
            selected = None
            for page in payload["pages"]:
                if isinstance(page, dict) and normalize_period(page.get("period", period)) == normalize_period(period):
                    selected = page.get("payload", page)
                    break
            payload = selected if selected is not None else {"status_code": "INFO-200", "data": []}
        body = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        return payload, body
