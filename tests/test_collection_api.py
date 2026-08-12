from __future__ import annotations

from typing import Any

import pytest

from collection.api import ApiClient, ApiError, FetchError


class FakeResponse:
    def __init__(
        self,
        status_code: int,
        payload: Any = None,
        *,
        url: str = "https://api.example.test/",
        headers: dict[str, str] | None = None,
        text: str = "",
        json_error: Exception | None = None,
    ) -> None:
        self.status_code = status_code
        self.payload = payload
        self.url = url
        self.headers = headers or {}
        self.text = text
        self.json_error = json_error

    def json(self) -> Any:
        if self.json_error is not None:
            raise self.json_error
        return self.payload


class FakeSession:
    def __init__(self, responses: list[FakeResponse]) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def get(self, url: str, **kwargs: Any) -> FakeResponse:
        self.calls.append({"url": url, **kwargs})
        return self.responses.pop(0)


def test_api_get_keeps_key_in_header_and_same_origin() -> None:
    session = FakeSession([FakeResponse(200, {"ok": True})])
    client = ApiClient("https://api.example.test", api_key="secret", session=session)

    assert client.get("/healthz") == {"ok": True}
    assert session.calls[0]["url"] == "https://api.example.test/healthz"
    assert session.calls[0]["headers"]["X-API-Key"] == "secret"
    assert "secret" not in session.calls[0]["url"]


def test_api_resolve_rejects_external_origin_and_secret_query() -> None:
    client = ApiClient("https://api.example.test", api_key="secret")

    with pytest.raises(FetchError) as origin_error:
        client.resolve("https://evil.example.test/api/v1/cars/cursor")
    assert origin_error.value.code == "source_allowlist"

    with pytest.raises(FetchError) as secret_error:
        client.resolve("/api/v1/cars/cursor", params={"api_key": "secret"})
    assert secret_error.value.code == "secret_query"


def test_api_refreshes_public_key_once_after_forbidden_response() -> None:
    session = FakeSession(
        [
            FakeResponse(403, {}, url="https://api.example.test/api/v1/cars/cursor"),
            FakeResponse(
                200,
                {"data": {"current": {"api_key": "new-key", "expires_at": "later"}}},
                url="https://api.example.test/api/v1/public-key",
            ),
            FakeResponse(200, {"data": [{"id": 1}]}, url="https://api.example.test/api/v1/cars/cursor"),
        ]
    )
    client = ApiClient("https://api.example.test", api_key="old-key", session=session)

    payload = client.get("/api/v1/cars/cursor", params={"after_id": 0, "limit": 500})

    assert payload == {"data": [{"id": 1}]}
    assert session.calls[0]["headers"]["X-API-Key"] == "old-key"
    assert "X-API-Key" not in session.calls[1]["headers"]
    assert session.calls[2]["headers"]["X-API-Key"] == "new-key"
    assert client.api_key == "new-key"


def test_api_invalid_json_is_a_stable_error() -> None:
    session = FakeSession([FakeResponse(200, json_error=ValueError("bad json"))])
    client = ApiClient("https://api.example.test", api_key="key", session=session)

    with pytest.raises(ApiError) as exc_info:
        client.get("/healthz")

    assert exc_info.value.code == "json_schema"
