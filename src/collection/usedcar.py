"""AutoData used-car cursor and change-log collectors.

This module returns source-shaped mappings only.  It does not normalize rows,
write a database, or own a polling loop.  The pipeline decides what to do
with each yielded ``Page``.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from threading import RLock
from typing import (
    Any,
    Callable,
    Dict,
    Iterable,
    Iterator,
    List,
    Mapping,
    Optional,
    Sequence,
)
from urllib.parse import parse_qsl, urlsplit, urlunsplit

from .api import ApiClient, FetchError


INITIAL_ENDPOINT = "/api/v1/cars/cursor"
CHANGES_ENDPOINT = "/api/v1/changes"
MAX_PAGE_LIMIT = 500


@dataclass(frozen=True)
class Page:
    records: List[Dict[str, Any]]
    meta: Dict[str, Any]
    next_url: Optional[str]

    @property
    def has_more(self) -> bool:
        """Read both common spellings; absent metadata follows ``next``."""

        if "has_more" in self.meta:
            return bool(self.meta["has_more"])
        if "hasMore" in self.meta:
            return bool(self.meta["hasMore"])
        return self.next_url is not None


# Compatibility name used by the first integration draft.
UsedCarPage = Page


def parse_page(payload: Any) -> Page:
    """Validate one documented AutoData page and preserve raw fields.

    ``data``, ``meta`` and ``links`` are required.  A source response with a
    missing envelope is an error, never an empty successful page.
    """

    if not isinstance(payload, Mapping):
        raise FetchError("response root must be an object", code="response_schema")
    for required in ("data", "meta", "links"):
        if required not in payload:
            raise FetchError(
                f"response is missing {required}",
                code="response_schema",
            )

    raw_data = payload["data"]
    raw_meta = payload["meta"]
    raw_links = payload["links"]
    if not isinstance(raw_data, list) or not all(
        isinstance(item, Mapping) for item in raw_data
    ):
        raise FetchError(
            "response data must be a list of objects", code="response_schema"
        )
    if not isinstance(raw_meta, Mapping) or not isinstance(raw_links, Mapping):
        raise FetchError(
            "response meta and links must be objects", code="response_schema"
        )

    raw_next = raw_links.get("next")
    if raw_next is not None and (not isinstance(raw_next, str) or not raw_next.strip()):
        raise FetchError(
            "links.next must be a URL string or null", code="response_schema"
        )

    records: List[Dict[str, Any]] = []
    for index, item in enumerate(raw_data):
        record = dict(item)
        nested_identifier = any(
            isinstance(record.get(key), Mapping)
            and (
                record[key].get("id") is not None
                or record[key].get("listingNumber") is not None
            )
            for key in ("record", "vehicle", "car", "payload", "entity", "data")
        )
        if (
            record.get("id") is None
            and record.get("listingNumber") is None
            and not nested_identifier
        ):
            raise FetchError(
                f"response data[{index}] must contain an identified vehicle object",
                code="response_schema",
            )
        # No field renaming or flattening is allowed at this stage.
        records.append(record)

    return Page(
        records=records,
        meta=dict(raw_meta),
        next_url=raw_next.strip() if isinstance(raw_next, str) else None,
    )


# Compatibility alias used by the first integration draft.
parse_used_car_page = parse_page


def _first_value(mapping: Mapping[str, Any], names: Sequence[str]) -> Any:
    for name in names:
        value = mapping.get(name)
        if value not in (None, ""):
            return value
    return None


def page_checkpoint(
    meta: Mapping[str, Any], records: Sequence[Mapping[str, Any]]
) -> Dict[str, Any]:
    """Extract checkpoint metadata without persisting response bodies."""

    last_id: Optional[int] = None
    last_seq: Optional[int] = None
    for record in records:
        raw_id = record.get("id")
        raw_seq = record.get("seq")
        if isinstance(raw_id, int) and not isinstance(raw_id, bool):
            if last_id is None or raw_id > last_id:
                last_id = raw_id
        if isinstance(raw_seq, int) and not isinstance(raw_seq, bool):
            if last_seq is None or raw_seq > last_seq:
                last_seq = raw_seq
    until_id = _first_value(meta, ("until_id", "untilId", "high_water_id"))
    explicit_high_water_seq = _first_value(
        meta,
        ("high_water_seq", "highWaterSeq", "last_seq"),
    )
    until_seq = _first_value(meta, ("until_seq", "untilSeq"))
    checkpoint = {
        "until_id": until_id if until_id is not None else last_id,
        "dataset_epoch": _first_value(meta, ("dataset_epoch", "datasetEpoch")),
        "high_water_seq": (
            explicit_high_water_seq if explicit_high_water_seq is not None else last_seq
        ),
    }
    if until_seq is not None:
        checkpoint["until_seq"] = until_seq
    return checkpoint


def _canonical_next_url(value: str) -> str:
    parsed = urlsplit(value)
    query_names = {
        name.lower().replace("-", "_") for name, _ in parse_qsl(parsed.query)
    }
    if query_names & ApiClient._SECRET_QUERY_NAMES:
        raise FetchError(
            "cursor next link contains a secret query parameter", code="secret_query"
        )
    return urlunsplit(parsed._replace(fragment=""))


class UsedCarFetcher:
    """Fetch a bounded initial or incremental sequence sequentially."""

    def __init__(
        self,
        client: Any,
        interval_seconds: float = 1.0,
        monotonic: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        if interval_seconds < 1.0:
            raise ValueError("interval_seconds must be at least 1 second")
        self.client = client
        self.interval_seconds = interval_seconds
        self._monotonic = monotonic
        self._sleeper = sleeper
        self._next_start: Optional[float] = None
        self._lock = RLock()

    def _wait_for_next_start(self) -> None:
        now = self._monotonic()
        if self._next_start is not None:
            self._sleeper(max(0.0, self._next_start - now))
        self._next_start = self._monotonic() + self.interval_seconds

    @staticmethod
    def _validate_next_path(next_url: str, expected_path: str) -> str:
        parsed = urlsplit(next_url)
        if parsed.scheme or parsed.netloc or parsed.path != expected_path:
            raise FetchError(
                "cursor next link points outside the documented endpoint",
                code="source_allowlist",
            )
        return _canonical_next_url(next_url)

    def _iter_pages(
        self,
        *,
        first_path: str,
        first_params: Mapping[str, Any],
        limit: int,
        max_batches: int,
    ) -> Iterator[Page]:
        if not 1 <= limit <= MAX_PAGE_LIMIT:
            raise ValueError(f"limit must be between 1 and {MAX_PAGE_LIMIT}")
        if max_batches <= 0:
            raise ValueError("max_batches must be greater than zero")

        next_url: Optional[str] = None
        seen_urls: set[str] = set()
        with self._lock:
            for batch_number in range(max_batches):
                self._wait_for_next_start()
                if next_url is None:
                    request_path = first_path
                    payload = self.client.get(request_path, params=dict(first_params))
                else:
                    request_path = next_url
                    if next_url in seen_urls:
                        raise FetchError(
                            "cursor next link repeated an already requested URL",
                            code="cursor_loop",
                        )
                    payload = self.client.get(next_url)
                seen_urls.add(_canonical_next_url(request_path))

                page = parse_page(payload)
                yield page

                if not page.has_more:
                    return
                if batch_number + 1 >= max_batches:
                    return
                if not page.next_url:
                    raise FetchError(
                        "cursor response says has_more but links.next is absent",
                        code="cursor_link_missing",
                    )
                next_url = self._validate_next_path(page.next_url, first_path)

    def iter_initial(self, limit: int, max_batches: int) -> Iterator[Page]:
        yield from self._iter_pages(
            first_path=INITIAL_ENDPOINT,
            first_params={"after_id": 0, "limit": limit},
            limit=limit,
            max_batches=max_batches,
        )

    def incremental_watermark(self) -> Dict[str, Any]:
        """Read the change-stream boundary that brackets an initial sync."""

        self._wait_for_next_start()
        payload = self.client.get(
            CHANGES_ENDPOINT,
            params={"after_seq": 0, "limit": 1},
        )
        page = parse_page(payload)
        state = page_checkpoint(page.meta, page.records)
        value = state.get("until_seq")
        if value is None:
            value = state.get("high_water_seq")
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise FetchError(
                "source does not provide a sequence watermark for initial loading",
                code="incremental_contract_missing",
            )
        return {
            "high_water_seq": value,
            "dataset_epoch": state.get("dataset_epoch"),
        }

    def iter_incremental(
        self, after_seq: int, limit: int, max_batches: int
    ) -> Iterator[Page]:
        if after_seq < 0:
            raise ValueError("after_seq must be non-negative")
        yield from self._iter_pages(
            first_path=CHANGES_ENDPOINT,
            first_params={"after_seq": after_seq, "limit": limit},
            limit=limit,
            max_batches=max_batches,
        )

    def fetch_initial(
        self, limit: int = MAX_PAGE_LIMIT, max_batches: int = 20
    ) -> List[Dict[str, Any]]:
        """Compatibility helper returning a flattened initial result."""

        return [
            record
            for page in self.iter_initial(limit, max_batches)
            for record in page.records
        ]

    def fetch_changes(
        self,
        after_seq: int,
        limit: int = MAX_PAGE_LIMIT,
        max_batches: int = 20,
    ) -> List[Dict[str, Any]]:
        return [
            record
            for page in self.iter_incremental(after_seq, limit, max_batches)
            for record in page.records
        ]

    def close(self) -> None:
        """Release transport resources owned by the API client."""

        close = getattr(self.client, "close", None)
        if close is not None:
            close()


def _fixture_pages(path: Path) -> List[Page]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FetchError(
            "fixture could not be read as JSON", code="fixture_error"
        ) from exc

    if isinstance(payload, Mapping) and isinstance(payload.get("pages"), list):
        raw_pages = payload["pages"]
    elif isinstance(payload, Mapping):
        raw_pages = [payload]
    else:
        raise FetchError(
            "fixture root must be an object with a page envelope", code="fixture_schema"
        )

    if not raw_pages:
        raise FetchError(
            "fixture must contain at least one page", code="fixture_schema"
        )
    pages: List[Page] = []
    for index, raw_page in enumerate(raw_pages):
        if not isinstance(raw_page, Mapping):
            raise FetchError(
                f"fixture page {index} must be an object", code="fixture_schema"
            )
        pages.append(parse_page(raw_page))
    return pages


class FixtureFetcher:
    """Finite, network-free fetcher using the same page parser as live data."""

    def __init__(self, path: Path) -> None:
        self.pages = _fixture_pages(path)

    def _iter(self, expected_path: str, limit: int, max_batches: int) -> Iterator[Page]:
        if not 1 <= limit <= MAX_PAGE_LIMIT:
            raise ValueError(f"limit must be between 1 and {MAX_PAGE_LIMIT}")
        if max_batches <= 0:
            raise ValueError("max_batches must be greater than zero")
        seen_next: set[str] = set()
        for index, page in enumerate(self.pages[:max_batches]):
            yield page
            if not page.has_more:
                return
            if index + 1 >= max_batches:
                return
            if not page.next_url:
                raise FetchError(
                    "fixture says has_more but links.next is absent",
                    code="cursor_link_missing",
                )
            next_url = UsedCarFetcher._validate_next_path(page.next_url, expected_path)
            if next_url in seen_next:
                raise FetchError("fixture cursor link repeated", code="cursor_loop")
            seen_next.add(next_url)
        if self.pages and self.pages[-1].has_more and len(self.pages) < max_batches:
            raise FetchError(
                "fixture ended before links.next was exhausted", code="fixture_schema"
            )

    def iter_initial(self, limit: int, max_batches: int) -> Iterator[Page]:
        yield from self._iter(INITIAL_ENDPOINT, limit, max_batches)

    def iter_incremental(
        self, after_seq: int, limit: int, max_batches: int
    ) -> Iterator[Page]:
        if after_seq < 0:
            raise ValueError("after_seq must be non-negative")
        yield from self._iter(CHANGES_ENDPOINT, limit, max_batches)

    def incremental_watermark(self) -> Dict[str, Any]:
        """Reuse a fixture page sequence marker as its initial watermark."""

        for page in self.pages:
            state = page_checkpoint(page.meta, page.records)
            value = state.get("until_seq")
            if value is None:
                value = state.get("high_water_seq")
            if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
                return {
                    "high_water_seq": value,
                    "dataset_epoch": state.get("dataset_epoch"),
                }
        raise FetchError(
            "fixture does not provide a sequence watermark for initial loading",
            code="incremental_contract_missing",
        )


def load_fetcher(settings: Any, fixture: Optional[Path]) -> Any:
    if fixture is not None:
        return FixtureFetcher(fixture)
    return UsedCarFetcher(
        ApiClient(settings),
        interval_seconds=float(getattr(settings, "interval_seconds", 1.0)),
    )


def collect_fixture_pages(
    pages: Iterable[Mapping[str, Any]],
    *,
    endpoint: str = INITIAL_ENDPOINT,
) -> List[Dict[str, Any]]:
    """Compatibility helper that applies the same parser to supplied pages."""

    if endpoint not in {INITIAL_ENDPOINT, CHANGES_ENDPOINT}:
        raise FetchError("fixture endpoint is not documented", code="source_allowlist")
    result: List[Dict[str, Any]] = []
    for page in pages:
        parsed = parse_page(page)
        result.extend(parsed.records)
        if not parsed.has_more:
            break
        if not parsed.next_url:
            raise FetchError(
                "fixture says has_more but links.next is absent",
                code="cursor_link_missing",
            )
        UsedCarFetcher._validate_next_path(parsed.next_url, endpoint)
    return result


__all__ = [
    "CHANGES_ENDPOINT",
    "INITIAL_ENDPOINT",
    "MAX_PAGE_LIMIT",
    "FetchError",
    "FixtureFetcher",
    "Page",
    "UsedCarPage",
    "UsedCarFetcher",
    "collect_fixture_pages",
    "load_fetcher",
    "page_checkpoint",
    "parse_page",
    "parse_used_car_page",
]
