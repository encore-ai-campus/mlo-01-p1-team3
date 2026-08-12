"""Statistics-Nuri automobile-registration source adapter."""

from __future__ import annotations

import hashlib
import json
import re
import ssl
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

from .api import ApiError


class RegistrationError(RuntimeError):
    """An upstream or response-envelope error for registration reports."""

    def __init__(self, message: str, code: str = "registration_error", *, retryable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable


RegistrationCollectionError = RegistrationError


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
    normalized = normalize_period(period)
    return f"{normalized[:4]}-{normalized[4:]}"


def add_month(period: str, offset: int) -> str:
    normalized = normalize_period(period)
    year, month = int(normalized[:4]), int(normalized[4:])
    serial = year * 12 + (month - 1) + int(offset)
    next_year, zero_month = divmod(serial, 12)
    return f"{next_year:04d}{zero_month + 1:02d}"


def current_period(time_zone: str = "Asia/Seoul") -> str:
    from zoneinfo import ZoneInfo

    return datetime.now(ZoneInfo(time_zone)).strftime("%Y%m")


def find_value(payload: Any, names: set[str]) -> Any:
    """Find a status/message field without guessing the record envelope."""

    if isinstance(payload, Mapping):
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


def _is_no_data_status(status: Any) -> bool:
    return status in {"INFO-200", 200, "200"}


def extract_record_list(payload: Any) -> List[Dict[str, Any]]:
    """Extract only the documented ``result_data.formList`` array.

    A generic recursive search is intentionally not used here: accepting an
    unrelated ``data`` or ``items`` field would turn a changed source schema
    into a false successful run.
    """

    if not isinstance(payload, Mapping):
        raise RegistrationError("registration response must be an object", "response_schema")
    status = find_value(payload, {"status_code", "statuscode"})
    if _is_no_data_status(status):
        return []

    result_data = payload.get("result_data")
    if not isinstance(result_data, Mapping):
        raise RegistrationError("registration response.result_data is missing", "response_schema")
    form_list = result_data.get("formList")
    if not isinstance(form_list, list):
        raise RegistrationError(
            "registration response.result_data.formList is missing",
            "response_schema",
        )
    records: List[Dict[str, Any]] = []
    for index, record in enumerate(form_list):
        if not isinstance(record, Mapping):
            raise RegistrationError(f"formList[{index}] must be an object", "response_schema")
        records.append(dict(record))
    return records


def _status_error(payload: Any) -> None:
    status = find_value(payload, {"status_code", "statuscode"})
    if status in {None, "", "INFO-000", 0, "0", "INFO-200", 200, "200"}:
        return
    if status in {"INFO-100", 100, "100"}:
        raise RegistrationError("registration API key is invalid", "invalid_api_key")
    if status in {"INFO-300", 300, "300"}:
        raise RegistrationError("registration API service is unavailable", "api_closed")
    message = find_value(payload, {"message", "resultmsg", "result_msg"})
    raise RegistrationError(
        f"registration API returned {status}: {message or 'unknown error'}",
        "api_error",
    )


def _ssl_context() -> ssl.SSLContext:
    """Use the platform CA store; this is portable on Windows and AWS."""

    return ssl.create_default_context()


class RegistrationApiClient:
    """One-period Statistics-Nuri client.

    This API's documented contract requires ``key`` in its query string.  The
    generic AutoData ``ApiClient`` never does that; this exception is isolated
    to the official registration endpoint adapter.
    """

    def __init__(self, settings: Any, *, max_retries: int = 2) -> None:
        api_url = str(getattr(settings, "registration_api_url", ""))
        parsed = urlsplit(api_url)
        if parsed.netloc != "stat.molit.go.kr":
            raise RegistrationError("registration endpoint is outside the approved host", "source_allowlist")
        api_key = getattr(settings, "registration_api_key", None)
        if not api_key:
            raise RegistrationError(
                "REGISTRATION_API_KEY or MOLIT_API_KEY is required",
                "missing_api_key",
            )
        if max_retries < 0:
            raise ValueError("max_retries must be non-negative")
        self.settings = settings
        self.max_retries = max_retries

    def fetch_period(
        self,
        period: str,
        reserve_call: Callable[[], None],
    ) -> Tuple[Any, bytes]:
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
            method="GET",
        )

        for attempt in range(self.max_retries + 1):
            # Retries consume quota too, so reserve before every attempt.
            reserve_call()
            try:
                with urlopen(
                    request,
                    timeout=float(self.settings.timeout_seconds),
                    context=_ssl_context(),
                ) as response:
                    body = response.read(8 * 1024 * 1024 + 1)
                    if len(body) > 8 * 1024 * 1024:
                        raise RegistrationError(
                            "registration response exceeded 8 MiB",
                            "response_too_large",
                        )
            except HTTPError as exc:
                body = exc.read(512 * 1024)
                if exc.code == 500 and b"INFO-100" in body:
                    raise RegistrationError("registration API key is invalid", "invalid_api_key") from exc
                if exc.code == 500 and b"INFO-200" in body:
                    empty_payload = {
                        "status_code": "INFO-200",
                        "result_data": {"formList": []},
                    }
                    return empty_payload, body
                if exc.code == 500 and b"INFO-300" in body:
                    raise RegistrationError("registration API service is unavailable", "api_closed") from exc
                if exc.code not in {408, 429, 500, 502, 503, 504} or attempt >= self.max_retries:
                    raise RegistrationError(
                        f"registration upstream HTTP {exc.code}",
                        f"http_{exc.code}",
                    ) from exc
                continue
            except (URLError, TimeoutError) as exc:
                if attempt >= self.max_retries:
                    raise ApiError(
                        "registration upstream connection failed",
                        code="connection_error",
                    ) from exc
                continue

            try:
                payload = json.loads(body.decode("utf-8-sig"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise RegistrationError("registration response is not valid JSON", "json_schema") from exc
            _status_error(payload)
            extract_record_list(payload)
            return payload, body

        raise ApiError("registration retry loop exhausted", code="retry_exhausted")


class FixtureRegistrationClient:
    """Fixture client that validates the same envelope as the live client."""

    def __init__(self, path: Path) -> None:
        try:
            self.payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RegistrationError("registration fixture could not be read", "fixture_error") from exc

    def fetch_period(
        self,
        period: str,
        reserve_call: Callable[[], None],
    ) -> Tuple[Any, bytes]:
        period = normalize_period(period)
        reserve_call()
        payload: Any = self.payload
        if isinstance(payload, Mapping) and isinstance(payload.get("pages"), list):
            selected: Any = None
            for page in payload["pages"]:
                if not isinstance(page, Mapping):
                    raise RegistrationError("registration fixture page must be an object", "fixture_schema")
                page_period = normalize_period(page.get("period", period))
                if page_period == period:
                    selected = page.get("payload", page)
                    break
            payload = selected if selected is not None else {
                "status_code": "INFO-200",
                "result_data": {"formList": []},
            }

        _status_error(payload)
        extract_record_list(payload)
        body = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        return payload, body


def response_hash(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


__all__ = [
    "FixtureRegistrationClient",
    "RegistrationApiClient",
    "RegistrationCollectionError",
    "RegistrationError",
    "RegistrationPage",
    "add_month",
    "current_period",
    "extract_record_list",
    "find_value",
    "month_label",
    "normalize_period",
    "response_hash",
]
