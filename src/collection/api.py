"""AutoData HTTP client used by the collection stage.

The client owns transport concerns only.  It validates the configured origin,
keeps API keys in ``X-API-Key`` headers, refreshes a key once after HTTP 403,
and converts upstream failures into stable ``ApiError`` objects.
"""

from __future__ import annotations

import json
import random
import time
from dataclasses import dataclass
from typing import Any, Mapping, MutableMapping, Optional, Sequence
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

import requests


class FetchError(RuntimeError):
    """A collection or source-response contract error."""

    def __init__(self, message: str, code: str = "fetch_error") -> None:
        super().__init__(message)
        self.code = code


class ApiError(FetchError):
    """An HTTP, network, or JSON response error without secret values."""

    def __init__(
        self,
        message: str,
        *,
        status: Optional[int] = None,
        status_code: Optional[int] = None,
        url: Optional[str] = None,
        retryable: bool = False,
        code: str = "api_error",
        retry_after: Optional[float] = None,
    ) -> None:
        super().__init__(message, code=code)
        self.status = status if status is not None else status_code
        # ``status_code`` is kept as a compatibility alias for the first
        # collection implementation.
        self.status_code = self.status
        self.url = url
        self.retryable = retryable
        self.retry_after = retry_after


@dataclass(frozen=True)
class PublicKeyInfo:
    active_from: Optional[str]
    expires_at: Optional[str]
    next_active_from: Optional[str]


def _nested_value(payload: Any, paths: Sequence[Sequence[str]]) -> Any:
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


def _extract_public_key(payload: Any) -> tuple[str, PublicKeyInfo]:
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
        raise ApiError(
            "public-key response did not contain data.current.api_key",
            code="key_schema",
        )

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
    """Bounded JSON/text client for the configured API origin.

    The normal constructor receives ``common.config.Settings``.  A URL form is
    also retained for the old ``collection.cars`` compatibility functions.
    """

    _SECRET_QUERY_NAMES = {
        "key",
        "api_key",
        "apikey",
        "access_token",
        "token",
        "authorization",
    }

    def __init__(
        self,
        settings_or_base_url: Any,
        *,
        api_key: Optional[str] = None,
        timeout: tuple[float, float] | float | None = None,
        session: Optional[requests.Session] = None,
        sleeper: Any = time.sleep,
    ) -> None:
        if isinstance(settings_or_base_url, str):
            raw_base_url = settings_or_base_url
            configured_key = None
            configured_timeout = 30.0
            configured_user_agent = "mlo-used-car-collector/0.1"
        else:
            raw_base_url = getattr(settings_or_base_url, "base_url", "")
            configured_key = getattr(settings_or_base_url, "api_key", None)
            configured_timeout = float(getattr(settings_or_base_url, "timeout_seconds", 30.0))
            configured_user_agent = str(
                getattr(settings_or_base_url, "user_agent", "mlo-used-car-collector/0.1")
            )

        parsed = urlsplit(str(raw_base_url).rstrip("/"))
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("base_url must be an absolute HTTP(S) URL")
        self.base_url = f"{parsed.scheme}://{parsed.netloc}"
        selected_key = api_key if api_key is not None else configured_key
        self.api_key = selected_key.strip() if isinstance(selected_key, str) and selected_key.strip() else None
        self.timeout = timeout if timeout is not None else configured_timeout
        self.user_agent = configured_user_agent
        self.session = session or requests.Session()
        self.sleeper = sleeper
        self.public_key_info: Optional[PublicKeyInfo] = None

    @classmethod
    def from_url(
        cls,
        url: str,
        *,
        api_key: Optional[str] = None,
        timeout: tuple[float, float] | float = (10, 30),
        session: Optional[requests.Session] = None,
    ) -> "ApiClient":
        parsed = urlsplit(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("url must be an absolute HTTP(S) URL")
        return cls(
            f"{parsed.scheme}://{parsed.netloc}",
            api_key=api_key,
            timeout=timeout,
            session=session,
        )

    @classmethod
    def _assert_no_secret_query(
        cls,
        url: str,
        params: Optional[Mapping[str, Any]],
    ) -> None:
        query_names = {name.lower().replace("-", "_") for name, _ in parse_qsl(urlsplit(url).query)}
        if params:
            query_names.update(str(name).lower().replace("-", "_") for name in params)
        leaked = query_names & cls._SECRET_QUERY_NAMES
        if leaked:
            raise FetchError(
                f"API key or secret must not be sent in query string: {sorted(leaked)}",
                code="secret_query",
            )

    def resolve(
        self,
        path_or_url: str,
        *,
        params: Optional[Mapping[str, Any]] = None,
        allowed_paths: Optional[Sequence[str]] = None,
    ) -> str:
        candidate = urljoin(f"{self.base_url}/", path_or_url.lstrip("/"))
        target = urlsplit(candidate)
        base = urlsplit(self.base_url)
        if (target.scheme, target.netloc) != (base.scheme, base.netloc):
            raise FetchError("endpoint is outside the configured API origin", code="source_allowlist")

        normalized_path = target.path.rstrip("/") or "/"
        if allowed_paths is not None:
            normalized_allowed = {path.rstrip("/") or "/" for path in allowed_paths}
            if normalized_path not in normalized_allowed:
                raise FetchError(
                    f"endpoint is not documented: {target.path}",
                    code="source_allowlist",
                )

        self._assert_no_secret_query(candidate, params)
        if params:
            existing = parse_qsl(target.query, keep_blank_values=True)
            merged = existing + [(str(key), value) for key, value in params.items()]
            target = target._replace(query=urlencode(merged, doseq=True))
        return urlunsplit(target)

    def _headers(self, headers: Optional[Mapping[str, str]], *, authenticated: bool) -> MutableMapping[str, str]:
        result = {str(key): str(value) for key, value in (headers or {}).items()}
        if authenticated and self.api_key:
            result.setdefault("X-API-Key", self.api_key)
        result.setdefault("Accept", "application/json")
        result.setdefault("User-Agent", self.user_agent)
        return result

    @staticmethod
    def _retry_after(response: Any) -> Optional[float]:
        raw = getattr(response, "headers", {}).get("Retry-After")
        if raw in (None, ""):
            return None
        try:
            return max(0.0, float(raw))
        except (TypeError, ValueError):
            return None

    def _request(self, url: str, *, headers: Mapping[str, str]) -> Any:
        try:
            response = self.session.get(url, headers=dict(headers), timeout=self.timeout)
        except requests.RequestException as exc:
            raise ApiError(
                "upstream connection failed",
                url=url,
                retryable=True,
                code="connection_error",
            ) from exc

        status = getattr(response, "status_code", None)
        if status is None:
            raise ApiError("upstream response has no HTTP status", url=url, code="http_error")
        if status >= 400:
            raise ApiError(
                f"upstream HTTP {status}",
                status=status,
                url=getattr(response, "url", url),
                retryable=status in {408, 429, 500, 502, 503, 504},
                code=f"http_{status}",
                retry_after=self._retry_after(response),
            )
        try:
            return response.json()
        except (TypeError, ValueError) as exc:
            raise ApiError("upstream response was not valid JSON", url=url, code="json_schema") from exc

    def get(
        self,
        path_or_url: str,
        *,
        params: Optional[Mapping[str, Any]] = None,
        authenticated: bool = True,
        allowed_paths: Optional[Sequence[str]] = None,
        max_attempts: int = 3,
    ) -> Any:
        if max_attempts <= 0:
            raise ValueError("max_attempts must be greater than zero")
        refreshed = False
        for attempt in range(max_attempts):
            if authenticated and not self.api_key:
                self.refresh_public_key()
            url = self.resolve(path_or_url, params=params, allowed_paths=allowed_paths)
            try:
                return self._request(url, headers=self._headers(None, authenticated=authenticated))
            except ApiError as exc:
                if authenticated and exc.status == 403 and not refreshed:
                    self.refresh_public_key()
                    refreshed = True
                    continue
                if not exc.retryable or attempt + 1 >= max_attempts:
                    raise
                delay = exc.retry_after if exc.retry_after is not None else min(8.0, 2.0**attempt)
                self.sleeper(delay + random.uniform(0.0, 0.25))
        raise ApiError("request retry loop exhausted", code="retry_exhausted")

    def get_json(
        self,
        path_or_url: str,
        *,
        params: Optional[Mapping[str, Any]] = None,
        headers: Optional[Mapping[str, str]] = None,
        allowed_paths: Optional[Sequence[str]] = None,
        authenticated: bool = True,
    ) -> Any:
        # Retained as a narrow compatibility alias.  Header-only key handling
        # still belongs to this client.
        if headers:
            url = self.resolve(path_or_url, params=params, allowed_paths=allowed_paths)
            merged = self._headers(headers, authenticated=authenticated)
            return self._request(url, headers=merged)
        return self.get(
            path_or_url,
            params=params,
            authenticated=authenticated,
            allowed_paths=allowed_paths,
        )

    def get_text(
        self,
        path_or_url: str,
        *,
        headers: Optional[Mapping[str, str]] = None,
        allowed_paths: Optional[Sequence[str]] = None,
        max_attempts: int = 3,
    ) -> str:
        url = self.resolve(path_or_url, allowed_paths=allowed_paths)
        request_headers = self._headers(headers, authenticated=False)
        request_headers["Accept"] = "text/html,application/xhtml+xml"
        for attempt in range(max_attempts):
            try:
                response = self.session.get(url, headers=dict(request_headers), timeout=self.timeout)
            except requests.RequestException as exc:
                error = ApiError("upstream connection failed", url=url, retryable=True, code="connection_error")
                if attempt + 1 >= max_attempts:
                    raise error from exc
                self.sleeper(min(8.0, 2.0**attempt))
                continue
            if response.status_code < 400:
                return response.text
            error = ApiError(
                f"upstream HTTP {response.status_code}",
                status=response.status_code,
                url=getattr(response, "url", url),
                retryable=response.status_code in {408, 429, 500, 502, 503, 504},
                code=f"http_{response.status_code}",
                retry_after=self._retry_after(response),
            )
            if not error.retryable or attempt + 1 >= max_attempts:
                raise error
            self.sleeper(error.retry_after if error.retry_after is not None else min(8.0, 2.0**attempt))
        raise ApiError("text request retry loop exhausted", code="retry_exhausted")

    def refresh_public_key(self) -> PublicKeyInfo:
        payload = self.get(
            "/api/v1/public-key",
            authenticated=False,
            allowed_paths=("/api/v1/public-key",),
            max_attempts=3,
        )
        key, info = _extract_public_key(payload)
        self.api_key = key
        self.public_key_info = info
        return info

    def health(self) -> Any:
        return self.get("/healthz", authenticated=False)


__all__ = ["ApiClient", "ApiError", "FetchError", "PublicKeyInfo"]
