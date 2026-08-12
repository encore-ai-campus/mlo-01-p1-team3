"""One-shot cursor and change-log fetchers for the used-car API."""

from __future__ import annotations

import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, Iterator, List, Mapping, Optional, Sequence
from urllib.parse import urlsplit

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from collection.api import ApiClient, ApiError
from common.config import Settings, settings_from_env


class FetchError(RuntimeError):
    """A bounded collection or response-envelope error."""

    def __init__(self, message: str, code: str = "fetch_error") -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class Page:
    records: List[Dict[str, Any]]
    meta: Dict[str, Any]
    next_url: Optional[str]

    @property
    def has_more(self) -> bool:
        return bool(self.meta.get("has_more") or self.meta.get("hasMore"))


def parse_page(payload: Mapping[str, Any]) -> Page:
    data = payload.get("data")
    if not isinstance(data, list) or not all(isinstance(item, dict) for item in data):
        raise FetchError("response data must be a list of objects", code="response_schema")
    raw_meta = payload.get("meta") or {}
    raw_links = payload.get("links") or {}
    if not isinstance(raw_meta, dict) or not isinstance(raw_links, dict):
        raise FetchError("response meta and links must be objects", code="response_schema")
    next_url = raw_links.get("next")
    if next_url is not None and not isinstance(next_url, str):
        raise FetchError("links.next must be a URL string", code="response_schema")
    return Page(records=data, meta=dict(raw_meta), next_url=next_url)


def _first_value(mapping: Mapping[str, Any], names: Sequence[str]) -> Any:
    for name in names:
        if mapping.get(name) not in (None, ""):
            return mapping[name]
    return None


def page_checkpoint(meta: Mapping[str, Any], records: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """Extract only checkpoint metadata; never persist the response body."""

    last_id = None
    last_seq = None
    for record in records:
        raw_id = record.get("id")
        raw_seq = record.get("seq")
        if isinstance(raw_id, int) and (last_id is None or raw_id > last_id):
            last_id = raw_id
        if isinstance(raw_seq, int) and (last_seq is None or raw_seq > last_seq):
            last_seq = raw_seq
    return {
        "until_id": _first_value(meta, ("until_id", "untilId", "high_water_id")) or last_id,
        "dataset_epoch": _first_value(meta, ("dataset_epoch", "datasetEpoch")),
        "high_water_seq": _first_value(
            meta,
            ("high_water_seq", "highWaterSeq", "until_seq", "untilSeq", "last_seq"),
        )
        or last_seq,
    }


class UsedCarFetcher:
    """Fetch a finite set of cursor or change pages; never owns a polling loop."""

    def __init__(
        self,
        client: ApiClient,
        interval_seconds: float = 1.0,
        monotonic: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self.client = client
        self.interval_seconds = interval_seconds
        self._monotonic = monotonic
        self._sleeper = sleeper
        self._next_start: Optional[float] = None

    def _wait_for_next_start(self) -> None:
        now = self._monotonic()
        if self._next_start is not None:
            self._sleeper(max(0.0, self._next_start - now))
        self._next_start = self._monotonic() + self.interval_seconds

    @staticmethod
    def _validate_next_path(next_url: str, expected_path: str) -> str:
        path = urlsplit(next_url).path
        if path != expected_path:
            raise FetchError(
                "cursor next link points outside the documented endpoint",
                code="source_allowlist",
            )
        return next_url

    def iter_initial(self, limit: int, max_batches: int) -> Iterator[Page]:
        next_url: Optional[str] = None
        for batch_number in range(max_batches):
            self._wait_for_next_start()
            if next_url:
                payload = self.client.get(next_url)
            else:
                payload = self.client.get(
                    "/api/v1/cars/cursor",
                    params={"after_id": 0, "limit": limit},
                )
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
            next_url = self._validate_next_path(page.next_url, "/api/v1/cars/cursor")

    def iter_incremental(self, after_seq: int, limit: int, max_batches: int) -> Iterator[Page]:
        next_url: Optional[str] = None
        for batch_number in range(max_batches):
            self._wait_for_next_start()
            if next_url:
                payload = self.client.get(next_url)
            else:
                payload = self.client.get(
                    "/api/v1/changes",
                    params={"after_seq": after_seq, "limit": limit},
                )
            page = parse_page(payload)
            yield page
            if not page.has_more:
                return
            if batch_number + 1 >= max_batches:
                return
            if not page.next_url:
                raise FetchError(
                    "changes response says has_more but links.next is absent",
                    code="changes_link_missing",
                )
            next_url = self._validate_next_path(page.next_url, "/api/v1/changes")


def _fixture_pages(path: Path) -> List[Page]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FetchError("fixture could not be read as JSON", code="fixture_error") from exc

    if isinstance(payload, dict) and isinstance(payload.get("pages"), list):
        raw_pages = payload["pages"]
    elif isinstance(payload, dict):
        raw_pages = [payload]
    elif isinstance(payload, list):
        raw_pages = [{"data": payload, "meta": {"has_more": False}, "links": {}}]
    else:
        raise FetchError("fixture root must be an object or list", code="fixture_schema")

    pages: List[Page] = []
    for raw_page in raw_pages:
        if not isinstance(raw_page, dict):
            raise FetchError("fixture pages must be objects", code="fixture_schema")
        pages.append(parse_page(raw_page))
    if not pages:
        raise FetchError("fixture must contain at least one page", code="fixture_schema")
    return pages


class FixtureFetcher:
    """Finite fetcher used by local tests; it has no network side effects."""

    def __init__(self, path: Path) -> None:
        self.pages = _fixture_pages(path)

    def iter_initial(self, limit: int, max_batches: int) -> Iterator[Page]:
        del limit
        yield from self.pages[:max_batches]

    def iter_incremental(self, after_seq: int, limit: int, max_batches: int) -> Iterator[Page]:
        del after_seq, limit
        yield from self.pages[:max_batches]


def load_fetcher(settings: Settings, fixture: Optional[Path]) -> Any:
    if fixture:
        return FixtureFetcher(fixture)
    return UsedCarFetcher(ApiClient(settings), interval_seconds=settings.interval_seconds)


def main(argv: Optional[Sequence[str]] = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Fetch one bounded used-car API cycle")
    parser.add_argument("--mode", choices=("initial", "incremental"), default="initial")
    parser.add_argument("--fixture", type=Path)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--max-batches", type=int)
    args = parser.parse_args(argv)

    try:
        settings = settings_from_env()
        fetcher = load_fetcher(settings, args.fixture)
        limit = args.limit or settings.batch_size
        max_batches = args.max_batches or settings.max_batches
        if limit <= 0 or limit > 500:
            raise ValueError("--limit must be between 1 and 500")
        if max_batches <= 0:
            raise ValueError("--max-batches must be greater than zero")
        after_seq = 0
        iterator = (
            fetcher.iter_initial(limit, max_batches)
            if args.mode == "initial"
            else fetcher.iter_incremental(after_seq, limit, max_batches)
        )
        pages = list(iterator)
        count = sum(len(page.records) for page in pages)
        print(json.dumps({"status": "OK", "mode": args.mode, "pages": len(pages), "records": count}))
        return 0
    except (ApiError, FetchError, ValueError) as exc:
        print(
            json.dumps({"status": "FAILED", "error_code": getattr(exc, "code", "fetch_error")}),
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
