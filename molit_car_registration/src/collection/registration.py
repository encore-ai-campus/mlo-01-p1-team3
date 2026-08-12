"""통계누리 자동차등록 Open API 수집기."""

from __future__ import annotations

import hashlib
import json
import re
import ssl
from datetime import datetime
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from common.config import Settings

try:
    import truststore
except ImportError:  # pragma: no cover - 환경에 패키지가 없으면 기본 SSL로 fallback
    truststore = None


class RegistrationCollectionError(RuntimeError):
    def __init__(self, message: str, code: str = "registration_collection_error"):
        super().__init__(message)
        self.code = code


def normalize_period(value: Any) -> str:
    digits = re.sub(r"[^0-9]", "", str(value or ""))
    if len(digits) != 6 or not 1 <= int(digits[4:]) <= 12:
        raise RegistrationCollectionError("period must be YYYYMM", "invalid_period")
    return digits


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


def extract_record_list(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        for key, value in payload.items():
            if str(key).lower() in {"date", "data", "items", "item", "rows", "row", "result"}:
                records = extract_record_list(value)
                if records:
                    return records
        for value in payload.values():
            records = extract_record_list(value)
            if records:
                return records
    elif isinstance(payload, list):
        records = [item for item in payload if isinstance(item, dict)]
        if records:
            return records
        for item in payload:
            records = extract_record_list(item)
            if records:
                return records
    return []


def _ssl_context() -> ssl.SSLContext:
    """Windows 인증서 저장소를 우선 사용하고, truststore가 없으면 기본 SSL을 사용합니다."""
    if truststore is not None:
        return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    return ssl.create_default_context()


class RegistrationApiClient:
    def __init__(self, settings: Settings):
        if not settings.registration_api_key:
            raise RegistrationCollectionError("REGISTRATION_API_KEY or MOLIT_API_KEY is required", "missing_api_key")
        if "stat.molit.go.kr" not in settings.registration_api_url:
            raise RegistrationCollectionError("registration endpoint is not approved", "source_allowlist")
        self.settings = settings

    def fetch_period(self, period: str, reserve_call: Callable[[], None]) -> tuple[Any, bytes]:
        period = normalize_period(period)
        query = urlencode(
            {
                "key": self.settings.registration_api_key,
                "form_id": self.settings.registration_form_id,
                "style_num": self.settings.registration_style_num,
                "start_dt": period,
                "end_dt": period,
            }
        )
        request = Request(
            f"{self.settings.registration_api_url}?{query}",
            headers={
                "Accept": "application/json, text/plain, */*",
                "User-Agent": self.settings.user_agent,
                "Referer": self.settings.registration_source_page,
            },
        )
        reserve_call()
        try:
            with urlopen(request, timeout=self.settings.timeout_seconds, context=_ssl_context()) as response:
                body = response.read()
        except HTTPError as exc:
            body = exc.read(512 * 1024)
            if exc.code == 500 and b"INFO-200" in body:
                return {"status_code": "INFO-200", "data": []}, body
            if exc.code == 500 and (b"INFO-100" in body or "인증키".encode() in body):
                raise RegistrationCollectionError("API key is invalid", "invalid_api_key") from exc
            if exc.code == 500:
                return {"status_code": "INFO-200", "data": []}, body
            raise RegistrationCollectionError(f"upstream HTTP {exc.code}", f"http_{exc.code}") from exc
        except (URLError, TimeoutError) as exc:
            raise RegistrationCollectionError(f"upstream connection failed: {exc}", "connection_error") from exc

        try:
            payload = json.loads(body.decode("utf-8-sig"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RegistrationCollectionError("response is not valid JSON", "json_schema") from exc
        status = find_value(payload, {"status_code", "statuscode"})
        if status in {"INFO-100", 100}:
            raise RegistrationCollectionError("API key is invalid", "invalid_api_key")
        if status == "INFO-300":
            raise RegistrationCollectionError("API service is unavailable", "api_closed")
        if status not in {None, "", "INFO-000", 0, "0", "INFO-200", 200, "200"}:
            raise RegistrationCollectionError(f"API returned {status}", "api_error")
        return payload, body


class FixtureRegistrationClient:
    def __init__(self, path: Path):
        try:
            self.payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RegistrationCollectionError("fixture could not be read", "fixture_error") from exc

    def fetch_period(self, period: str, reserve_call: Callable[[], None]) -> tuple[Any, bytes]:
        reserve_call()
        body = json.dumps(self.payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        return self.payload, body


def response_hash(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()
