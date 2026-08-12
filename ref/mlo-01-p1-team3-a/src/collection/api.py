"""HTTP client for the AutoData Lab used-car API.

The API documentation specifies a daily public key and requires the key in
the ``X-API-Key`` or Bearer header.  This module never puts the key in a query
string and never prints the key.  It is also executable once for a connection
smoke test:

    python -c "from collection.api import ApiClient"
"""

from __future__ import annotations

import json
import random
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence, Tuple
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urljoin, urlsplit, urlunsplit
from urllib.request import Request, urlopen

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from common.config import Settings, settings_from_env


class ApiError(RuntimeError):
    """A sanitized upstream or response-shape error."""

    def __init__(
        self,
        message: str,
        *,
        status: Optional[int] = None,
        retryable: bool = False,
        code: str = "api_error",
        retry_after: Optional[float] = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.retryable = retryable
        self.code = code
        self.retry_after = retry_after


@dataclass(frozen=True)
class PublicKeyInfo:
    active_from: Optional[str]
    expires_at: Optional[str]
    next_active_from: Optional[str]


def _nested_value(payload: Any, paths: Sequence[Tuple[str, ...]]) -> Any:
    for path in paths:
        value = payload
        for key in path:
            if not isinstance(value, Mapping):
                value = None
                break
            value = value.get(key)
        if value not in (None, ""):
            return value
    return None


def _extract_public_key(payload: Any) -> Tuple[str, PublicKeyInfo]:
    key = _nested_value(
        payload,
        (
            ("data", "current", "api_key"),
            ("data", "current", "apiKey"),
            ("current", "api_key"),
            ("current", "apiKey"),
            ("api_key",),
            ("apiKey",),
        ),
    )
    if not isinstance(key, str) or not key.strip():
        raise ApiError("public key response did not contain data.current.api_key", code="key_schema")

    info = PublicKeyInfo(
        active_from=_nested_value(
            payload,
            (("data", "current", "active_from"), ("data", "current", "activeFrom")),
        ),
        expires_at=_nested_value(
            payload,
            (("data", "current", "expires_at"), ("data", "current", "expiresAt")),
        ),
        next_active_from=_nested_value(
            payload,
            (("data", "next", "active_from"), ("data", "next", "activeFrom")),
        ),
    )
    return key.strip(), info


class ApiClient:
    """Bounded JSON client with one authorized key refresh after HTTP 403."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.base_url = settings.base_url.rstrip("/")
        self.api_key = settings.api_key
        self.public_key_info: Optional[PublicKeyInfo] = None

    def _safe_url(self, path_or_url: str, params: Optional[Mapping[str, Any]] = None) -> str:
        if path_or_url.startswith("http://") or path_or_url.startswith("https://"):
            candidate = path_or_url
        else:
            candidate = urljoin(self.base_url + "/", path_or_url.lstrip("/"))

        base = urlsplit(self.base_url)
        target = urlsplit(candidate)
        if (target.scheme, target.netloc) != (base.scheme, base.netloc):
            raise ApiError("next link points outside configured BASE_URL", code="source_allowlist")

        if params:
            query = urlencode(params, doseq=True)
            target = target._replace(query=query)
        return urlunsplit(target)

    def _request_json(
        self,
        path_or_url: str,
        *,
        params: Optional[Mapping[str, Any]] = None,
        authenticated: bool,
        allow_key_refresh: bool = True,
    ) -> Dict[str, Any]:
        url = self._safe_url(path_or_url, params)
        headers = {
            "Accept": "application/json",
            "User-Agent": self.settings.user_agent,
        }
        if authenticated:
            if not self.api_key:
                self.refresh_public_key()
            if not self.api_key:
                raise ApiError("API key is unavailable", code="missing_api_key")
            headers["X-API-Key"] = self.api_key

        request = Request(url, headers=headers, method="GET")
        try:
            with urlopen(request, timeout=self.settings.timeout_seconds) as response:
                raw = response.read(8 * 1024 * 1024 + 1)
                if len(raw) > 8 * 1024 * 1024:
                    raise ApiError("response exceeded 8 MiB limit", code="response_too_large")
        except HTTPError as exc:
            if authenticated and allow_key_refresh and exc.code == 403:
                self.refresh_public_key()
                return self._request_json(
                    path_or_url,
                    params=params,
                    authenticated=True,
                    allow_key_refresh=False,
                )
            retryable = exc.code in {429, 500, 502, 503, 504}
            code = "http_403" if exc.code == 403 else f"http_{exc.code}"
            retry_after = None
            if exc.headers:
                raw_retry_after = exc.headers.get("Retry-After")
                if raw_retry_after:
                    try:
                        retry_after = max(0.0, float(raw_retry_after))
                    except ValueError:
                        retry_after = None
            raise ApiError(
                f"upstream HTTP {exc.code}",
                status=exc.code,
                retryable=retryable,
                code=code,
                retry_after=retry_after,
            ) from exc
        except URLError as exc:
            raise ApiError("upstream connection failed", retryable=True, code="connection_error") from exc
        except TimeoutError as exc:
            raise ApiError("upstream request timed out", retryable=True, code="timeout") from exc

        try:
            payload = json.loads(raw.decode("utf-8-sig"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ApiError("upstream response was not valid JSON", code="json_schema") from exc
        if not isinstance(payload, dict):
            raise ApiError("upstream JSON root must be an object", code="json_schema")
        return payload

    def refresh_public_key(self) -> PublicKeyInfo:
        payload = self._request_json(
            "/api/v1/public-key",
            authenticated=False,
            allow_key_refresh=False,
        )
        key, info = _extract_public_key(payload)
        self.api_key = key
        self.public_key_info = info
        return info

    def get(
        self,
        path_or_url: str,
        *,
        params: Optional[Mapping[str, Any]] = None,
        authenticated: bool = True,
    ) -> Dict[str, Any]:
        for attempt in range(3):
            try:
                return self._request_json(
                    path_or_url,
                    params=params,
                    authenticated=authenticated,
                )
            except ApiError as exc:
                if not exc.retryable or attempt == 2:
                    raise
                backoff = min(8.0, 2.0**attempt) + random.uniform(0.0, 0.25)
                time.sleep(max(backoff, exc.retry_after or 0.0))
        raise ApiError("request retry loop exhausted", code="retry_exhausted")

    def health(self) -> Dict[str, Any]:
        return self.get("/healthz", authenticated=False)


def main(argv: Optional[Sequence[str]] = None) -> int:
    del argv
    try:
        settings = settings_from_env()
        client = ApiClient(settings)
        info = client.refresh_public_key()
        result = {
            "status": "OK",
            "base_url": settings.base_url,
            "public_key_loaded": True,
            "active_from": info.active_from,
            "expires_at": info.expires_at,
            "next_active_from": info.next_active_from,
        }
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except (ApiError, ValueError) as exc:
        print(
            json.dumps(
                {"status": "FAILED", "error_code": getattr(exc, "code", "config_error")},
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
