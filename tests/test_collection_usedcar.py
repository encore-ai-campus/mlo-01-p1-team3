from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from collection.usedcar import (
    CHANGES_ENDPOINT,
    INITIAL_ENDPOINT,
    FixtureFetcher,
    FetchError,
    UsedCarFetcher,
    collect_fixture_pages,
    load_fetcher,
    page_checkpoint,
    parse_page,
)


def page(records: list[dict[str, Any]], next_url: str | None = None) -> dict[str, Any]:
    return {"data": records, "meta": {}, "links": {"next": next_url}}


class QueueClient:
    def __init__(self, pages: list[dict[str, Any]]) -> None:
        self.pages = list(pages)
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def get(self, path: str, **kwargs: Any) -> dict[str, Any]:
        self.calls.append((path, kwargs))
        return self.pages.pop(0)


class Clock:
    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


def test_initial_collection_uses_cursor_contract_and_follows_next() -> None:
    next_url = f"{INITIAL_ENDPOINT}?after_id=101&limit=500"
    client = QueueClient([page([{"id": 101}], next_url), page([{"id": 102}])])
    clock = Clock()
    fetcher = UsedCarFetcher(client, monotonic=clock.monotonic, sleeper=clock.sleep)

    result = list(fetcher.iter_initial(limit=500, max_batches=2))

    assert [record for item in result for record in item.records] == [{"id": 101}, {"id": 102}]
    assert client.calls == [
        (INITIAL_ENDPOINT, {"params": {"after_id": 0, "limit": 500}}),
        (next_url, {}),
    ]
    assert clock.sleeps == [1.0]


def test_incremental_collection_uses_after_sequence_and_limit() -> None:
    client = QueueClient([page([{"id": 9, "seq": 18}])])
    fetcher = UsedCarFetcher(client, sleeper=lambda seconds: None)

    result = list(fetcher.iter_incremental(after_seq=17, limit=500, max_batches=1))

    assert result[0].records == [{"id": 9, "seq": 18}]
    assert client.calls == [
        (CHANGES_ENDPOINT, {"params": {"after_seq": 17, "limit": 500}})
    ]


def test_cursor_next_must_be_relative_and_stay_on_documented_endpoint() -> None:
    client = QueueClient([page([{"id": 1}], "https://evil.example/api/v1/cars/cursor?after_id=1")])
    fetcher = UsedCarFetcher(client, sleeper=lambda seconds: None)

    with pytest.raises(FetchError, match="outside the documented endpoint"):
        list(fetcher.iter_initial(limit=500, max_batches=2))


def test_cursor_loop_is_rejected() -> None:
    next_url = f"{INITIAL_ENDPOINT}?after_id=1&limit=500"
    client = QueueClient([page([{"id": 1}], next_url), page([{"id": 2}], next_url)])
    fetcher = UsedCarFetcher(client, sleeper=lambda seconds: None)

    with pytest.raises(FetchError) as exc_info:
        list(fetcher.iter_initial(limit=500, max_batches=3))

    assert exc_info.value.code == "cursor_loop"


def test_parse_page_rejects_missing_envelope_or_identifier() -> None:
    with pytest.raises(FetchError) as envelope_error:
        parse_page({"data": []})
    assert envelope_error.value.code == "response_schema"

    with pytest.raises(FetchError) as identifier_error:
        parse_page({"data": [{"brand": "missing-id"}], "meta": {}, "links": {}})
    assert identifier_error.value.code == "response_schema"


def test_page_checkpoint_prefers_high_water_metadata() -> None:
    checkpoint = page_checkpoint(
        {"until_id": 100, "dataset_epoch": "epoch-1", "high_water_seq": 55},
        [{"id": 99, "seq": 54}],
    )

    assert checkpoint == {
        "until_id": 100,
        "dataset_epoch": "epoch-1",
        "high_water_seq": 55,
    }


def test_fixture_fetcher_uses_the_same_cursor_parser(tmp_path: Path) -> None:
    next_url = f"{INITIAL_ENDPOINT}?after_id=1&limit=500"
    fixture = tmp_path / "usedcar.json"
    fixture.write_text(
        json.dumps({"pages": [page([{"id": 1}], next_url), page([{"id": 2}])]}),
        encoding="utf-8",
    )

    fetcher = FixtureFetcher(fixture)
    records = [record for item in fetcher.iter_initial(500, 2) for record in item.records]

    assert records == [{"id": 1}, {"id": 2}]
    assert load_fetcher(object(), fixture).__class__ is FixtureFetcher


def test_collect_fixture_pages_rejects_unknown_endpoint() -> None:
    with pytest.raises(FetchError) as exc_info:
        collect_fixture_pages([page([{"id": 1}])], endpoint="/api/v1/unknown")

    assert exc_info.value.code == "source_allowlist"
