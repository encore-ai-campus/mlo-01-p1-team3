from __future__ import annotations

from typing import Any

import collection.cars as cars


def test_legacy_get_api_key_uses_common_client(monkeypatch: Any) -> None:
    class FakeClient:
        api_key = None

        def __init__(self, settings: Any) -> None:
            self.settings = settings

        def refresh_public_key(self) -> None:
            self.api_key = "refreshed-key"

    monkeypatch.setattr(cars, "ApiClient", FakeClient)

    assert cars.get_api_key(object()) == "refreshed-key"


def test_legacy_request_api_returns_payload_and_current_key(monkeypatch: Any) -> None:
    class FakeClient:
        api_key = "new-key"

        @classmethod
        def from_url(cls, url: str, *, api_key: str) -> "FakeClient":
            instance = cls()
            instance.url = url
            instance.old_key = api_key
            return instance

        def get(self, url: str, *, authenticated: bool) -> dict[str, Any]:
            assert authenticated is True
            return {"data": [{"id": 1}]}

    monkeypatch.setattr(cars, "ApiClient", FakeClient)

    assert cars.request_api("https://api.example.test/api/v1/cars/cursor", "old-key") == (
        {"data": [{"id": 1}]},
        "new-key",
    )
