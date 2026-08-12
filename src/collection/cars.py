"""Compatibility entry points for the older used-car pipelines.

The canonical collector is ``collection.usedcar.UsedCarFetcher``.  These two
small functions keep the old callers working while using the same header-only
``ApiClient`` transport.
"""

from __future__ import annotations

from typing import Any, Optional
from .api import ApiClient, ApiError, FetchError
from .usedcar import (
    CHANGES_ENDPOINT,
    INITIAL_ENDPOINT,
    FixtureFetcher,
    Page,
    UsedCarFetcher,
    UsedCarPage,
    load_fetcher,
    page_checkpoint,
    parse_page,
    parse_used_car_page,
)


def _settings_from_env() -> Any:
    # Environment access remains inside common.config.Settings.
    from common.config import settings_from_env

    return settings_from_env()


def get_api_key(settings: Optional[Any] = None) -> str:
    """Fetch the current public key without putting it in a query string."""

    selected_settings = settings or _settings_from_env()
    client = ApiClient(selected_settings)
    client.refresh_public_key()
    if not client.api_key:
        raise FetchError("public-key response did not contain a usable api_key", code="key_schema")
    return client.api_key


def request_api(url: str, api_key: str) -> tuple[Any, str]:
    """Legacy one-request helper returning ``(payload, current_key)``."""

    client = ApiClient.from_url(url, api_key=api_key)
    payload = client.get(url, authenticated=True)
    return payload, client.api_key or ""


__all__ = [
    "ApiClient",
    "ApiError",
    "CHANGES_ENDPOINT",
    "FetchError",
    "FixtureFetcher",
    "INITIAL_ENDPOINT",
    "Page",
    "UsedCarFetcher",
    "UsedCarPage",
    "get_api_key",
    "load_fetcher",
    "page_checkpoint",
    "parse_page",
    "parse_used_car_page",
    "request_api",
]
