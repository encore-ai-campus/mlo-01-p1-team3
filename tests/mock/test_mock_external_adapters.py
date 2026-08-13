from __future__ import annotations

import json
import sys
from copy import deepcopy
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from urllib.error import HTTPError, URLError

import pytest
import requests

import collection.api as api_module
import collection.registration as registration_collection
from collection.api import ApiClient, ApiError, FetchError
from collection.faq import FaqCollector, FaqError, MAX_FAQ_BODY_BYTES, parse_faq_html
from collection.registration import RegistrationApiClient, RegistrationError
from common.config import Settings
from common.contracts import LoadStats
from loading.faq import MongoFaqUpsertSink
from loading.registration import (
    QuotaExceeded,
    SqlQuotaLedger,
    SqlRegistrationUpsertSink,
)
from migrations.mongo.ensure_indexes import FAQ_VALIDATOR


def _settings(tmp_path: Path) -> Settings:
    return Settings.from_env(
        {
            "USED_CAR_BASE_URL": "https://cars.example.test",
            "USED_CAR_API_KEY": "mock-key",
            "OUTPUT_DIR": str(tmp_path),
            "LOG_PATH": str(tmp_path / "events.jsonl"),
            "USED_CAR_BATCH_SIZE": "500",
            "USED_CAR_INITIAL_TARGET": "500",
            "USED_CAR_MAX_BATCHES": "1",
            "USED_CAR_INTERVAL_SECONDS": "1",
            "FAQ_SOURCE_URL": "https://faq.example.test/faqs",
            "FAQ_ALLOWED_PATHS": "/faqs",
            "FAQ_INTERVAL_SECONDS": "1",
            "FAQ_MAX_PAGES": "2",
            "FAQ_MAX_QUESTIONS_PER_PAGE": "10",
            "REGISTRATION_API_KEY": "mock-registration-key",
            "REGISTRATION_DAILY_QUOTA": "3",
            "SQL_HOST": "sql.example.test",
            "SQL_USER": "mock-user",
            "SQL_PASSWORD": "mock-password",
            "MONGODB_URI": "mongodb://mock-user:mock-password@mongo.example.test:27017/",
        },
        dotenv_path=tmp_path / "missing.env",
    )


class _Response:
    def __init__(
        self,
        status_code: int,
        payload: Any = None,
        *,
        headers: dict[str, str] | None = None,
        text: str = "",
        url: str = "https://cars.example.test/api/v1/cars/cursor",
    ) -> None:
        self.status_code = status_code
        self.payload = payload
        self.headers = headers or {}
        self.text = text
        self.url = url

    def json(self) -> Any:
        return self.payload


class _QueueSession:
    def __init__(self, outcomes: list[Any]) -> None:
        self.outcomes = list(outcomes)
        self.calls: list[dict[str, Any]] = []
        self.closed = False

    def get(self, url: str, **kwargs: Any) -> Any:
        self.calls.append({"url": url, **kwargs})
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    def close(self) -> None:
        self.closed = True


def test_api_client_close_releases_http_session() -> None:
    session = _QueueSession([])
    client = ApiClient(
        "https://cars.example.test",
        api_key="key",
        session=session,
    )

    client.close()

    assert session.closed is True


def test_api_mock_retries_connection_and_rate_limit_then_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _QueueSession(
        [
            requests.ConnectionError("mock connection failure"),
            _Response(429, headers={"Retry-After": "2.5"}),
            _Response(200, {"data": [{"id": 1}]}),
        ]
    )
    sleeps: list[float] = []
    monkeypatch.setattr(api_module.random, "uniform", lambda _start, _end: 0.0)
    client = ApiClient(
        "https://cars.example.test",
        api_key="secret-key",
        session=session,
        sleeper=sleeps.append,
    )

    result = client.get(
        "/api/v1/cars/cursor",
        params={"after_id": 0, "limit": 500},
        allowed_paths=("/api/v1/cars/cursor",),
    )

    assert result == {"data": [{"id": 1}]}
    assert sleeps == [1.0, 2.5]
    assert len(session.calls) == 3
    assert all(call["headers"]["X-API-Key"] == "secret-key" for call in session.calls)
    assert all("secret-key" not in call["url"] for call in session.calls)


def test_api_mock_text_retries_and_preserves_custom_headers() -> None:
    session = _QueueSession(
        [
            requests.Timeout("mock timeout"),
            _Response(503, headers={"Retry-After": "3"}),
            _Response(200, text="<html>ok</html>"),
        ]
    )
    sleeps: list[float] = []
    client = ApiClient(
        "https://faq.example.test",
        session=session,
        sleeper=sleeps.append,
    )

    body = client.get_text(
        "/faqs",
        headers={"User-Agent": "mock-agent"},
        allowed_paths=("/faqs",),
    )

    assert body == "<html>ok</html>"
    assert sleeps == [1.0, 3.0]
    assert session.calls[-1]["headers"]["User-Agent"] == "mock-agent"
    assert session.calls[-1]["headers"]["Accept"] == "text/html,application/xhtml+xml"


def test_api_mock_json_alias_headers_health_and_key_schema() -> None:
    session = _QueueSession(
        [
            _Response(200, {"ok": True}),
            _Response(200, {"status": "healthy"}),
            _Response(200, {"data": {"current": {}}}),
        ]
    )
    client = ApiClient("https://cars.example.test", api_key="key", session=session)

    assert client.get_json(
        "/healthz",
        headers={"X-Trace": "trace-1"},
        allowed_paths=("/healthz",),
        authenticated=False,
    ) == {"ok": True}
    assert session.calls[0]["headers"]["X-Trace"] == "trace-1"
    assert "X-API-Key" not in session.calls[0]["headers"]
    assert client.health() == {"status": "healthy"}
    with pytest.raises(ApiError) as exc_info:
        client.refresh_public_key()
    assert exc_info.value.code == "key_schema"


def test_api_mock_json_alias_with_headers_keeps_retry_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _QueueSession(
        [
            _Response(503, headers={"Retry-After": "2"}),
            _Response(200, {"ok": True}),
        ]
    )
    sleeps: list[float] = []
    monkeypatch.setattr(api_module.random, "uniform", lambda _start, _end: 0.0)
    client = ApiClient(
        "https://cars.example.test",
        api_key="key",
        session=session,
        sleeper=sleeps.append,
    )

    assert client.get_json(
        "/healthz",
        headers={"X-Trace": "trace-1"},
        allowed_paths=("/healthz",),
    ) == {"ok": True}
    assert sleeps == [2.0]
    assert [call["headers"]["X-Trace"] for call in session.calls] == [
        "trace-1",
        "trace-1",
    ]


def test_api_mock_json_alias_with_headers_keeps_403_key_refresh_contract() -> None:
    session = _QueueSession(
        [
            _Response(403),
            _Response(
                200,
                {"data": {"current": {"api_key": "new-key"}}},
                url="https://cars.example.test/api/v1/public-key",
            ),
            _Response(200, {"ok": True}),
        ]
    )
    client = ApiClient(
        "https://cars.example.test",
        api_key="old-key",
        session=session,
    )

    assert client.get_json(
        "/api/v1/cars/cursor",
        headers={"X-Trace": "trace-1"},
        allowed_paths=("/api/v1/cars/cursor",),
    ) == {"ok": True}
    assert session.calls[0]["headers"] == {
        "X-Trace": "trace-1",
        "X-API-Key": "old-key",
        "User-Agent": "mlo-used-car-collector/0.1",
        "Accept": "application/json",
    }
    assert "X-Trace" not in session.calls[1]["headers"]
    assert "X-API-Key" not in session.calls[1]["headers"]
    assert session.calls[2]["headers"]["X-Trace"] == "trace-1"
    assert session.calls[2]["headers"]["X-API-Key"] == "new-key"


@pytest.mark.parametrize(
    ("action", "error_type", "error_code"),
    [
        ("attempts", ValueError, None),
        ("missing_status", ApiError, "http_error"),
        ("unauthorized", ApiError, "http_401"),
        ("text_not_found", ApiError, "http_404"),
        ("path", FetchError, "source_allowlist"),
    ],
)
def test_api_mock_rejects_invalid_operating_responses(
    action: str, error_type: type[Exception], error_code: str | None
) -> None:
    if action == "missing_status":
        session = _QueueSession([SimpleNamespace(json=lambda: {})])
    elif action == "unauthorized":
        session = _QueueSession([_Response(401)])
    elif action == "text_not_found":
        session = _QueueSession([_Response(404)])
    else:
        session = _QueueSession([])
    client = ApiClient("https://cars.example.test", api_key="key", session=session)

    with pytest.raises(error_type) as exc_info:
        if action == "attempts":
            client.get("/healthz", max_attempts=0)
        elif action == "text_not_found":
            client.get_text("/healthz")
        elif action == "path":
            client.resolve("/undocumented", allowed_paths=("/healthz",))
        else:
            client.get("/healthz")
    if error_code is not None:
        assert getattr(exc_info.value, "code") == error_code


class _HtmlResponse:
    def __init__(
        self, body: bytes, content_type: str = "text/html; charset=utf-8"
    ) -> None:
        self.body = body
        self.headers = {"Content-Type": content_type}

    def __enter__(self) -> "_HtmlResponse":
        return self

    def __exit__(self, *_args: Any) -> None:
        return None

    def read(self, size: int = -1) -> bytes:
        return self.body if size < 0 else self.body[:size]


def _faq_html(*, next_url: str | None = None, count: int = 1) -> bytes:
    cards = "".join(
        f"""
        <article class="faq-item" data-faq-id="faq-{index}" data-brand="Brand A">
          <div data-field="category">Purchase</div>
          <div data-field="question">Question {index}</div>
          <div data-field="answer">Answer {index}</div>
          <time data-field="reviewed-at" datetime="2026-08-01"></time>
          <a data-field="source" href="https://source.example.test/faq-{index}">source</a>
        </article>
        """
        for index in range(count)
    )
    next_link = f'<a rel="next" href="{next_url}">next</a>' if next_url else ""
    return f"<html><body>{cards}{next_link}</body></html>".encode()


def test_faq_collector_mock_retries_http_and_connection_failures() -> None:
    outcomes: list[Any] = [
        HTTPError(
            "https://faq.example.test/faqs",
            429,
            "rate limited",
            {"Retry-After": "2"},
            None,
        ),
        URLError("mock DNS failure"),
        _HtmlResponse(_faq_html()),
    ]
    sleeps: list[float] = []

    def opener(_request: Any, timeout: float) -> Any:
        assert timeout == 30.0
        outcome = outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    settings = SimpleNamespace(
        faq_source_url="https://faq.example.test/faqs",
        faq_allowed_paths=("/faqs",),
        faq_interval_seconds=1.0,
        faq_max_pages=1,
        faq_max_questions_per_page=10,
        timeout_seconds=30.0,
        user_agent="mock-agent",
    )
    collector = FaqCollector(settings, opener=opener, sleeper=sleeps.append)

    assert list(collector.iter_pages())[0].records[0]["faq_id"] == "faq-0"
    assert sleeps == [2.0, 2.0]


@pytest.mark.parametrize(
    ("body", "source_url", "error_code"),
    [
        (b"", "https://faq.example.test/faqs", "faq_schema"),
        (b"\xff", "https://faq.example.test/faqs", "faq_encoding"),
        (_faq_html(), "", "source_allowlist"),
        (
            b"x" * (MAX_FAQ_BODY_BYTES + 1),
            "https://faq.example.test/faqs",
            "faq_response_too_large",
        ),
    ],
    ids=("empty", "invalid-utf8", "missing-source-url", "too-large"),
)
def test_faq_parser_mock_rejects_invalid_bodies(
    body: bytes, source_url: str, error_code: str
) -> None:
    with pytest.raises(FaqError) as exc_info:
        parse_faq_html(body, source_url)
    assert exc_info.value.code == error_code


def test_faq_collector_mock_rejects_content_type_loop_and_question_overflow() -> None:
    base = {
        "faq_source_url": "https://faq.example.test/faqs",
        "faq_allowed_paths": ("/faqs",),
        "faq_interval_seconds": 1.0,
        "faq_max_pages": 2,
        "faq_max_questions_per_page": 10,
        "timeout_seconds": 1.0,
        "user_agent": "mock-agent",
    }
    non_html = FaqCollector(
        SimpleNamespace(**base),
        opener=lambda *_args, **_kwargs: _HtmlResponse(b"{}", "application/json"),
    )
    with pytest.raises(FaqError) as content_error:
        list(non_html.iter_pages())
    assert content_error.value.code == "faq_content_type"

    looping = FaqCollector(
        SimpleNamespace(**base),
        opener=lambda *_args, **_kwargs: _HtmlResponse(_faq_html(next_url="/faqs")),
        sleeper=lambda _seconds: None,
    )
    with pytest.raises(FaqError) as loop_error:
        list(looping.iter_pages())
    assert loop_error.value.code == "faq_loop"

    complete_page = FaqCollector(
        SimpleNamespace(**{**base, "faq_max_questions_per_page": 1}),
        opener=lambda *_args, **_kwargs: _HtmlResponse(_faq_html(count=2)),
    )
    pages = list(complete_page.iter_pages())
    assert len(pages[0].records) == 2


def _registration_settings() -> Any:
    return SimpleNamespace(
        registration_api_url=(
            "https://stat.molit.go.kr/portal/openapi/service/rest/getList.do"
        ),
        registration_api_key="mock-registration-key",
        registration_form_id=5498,
        registration_style_num=2,
        registration_source_page="https://stat.molit.go.kr/",
        user_agent="mock-agent",
        timeout_seconds=1.0,
    )


class _RegistrationResponse:
    def __init__(self, body: bytes) -> None:
        self.body = body

    def __enter__(self) -> "_RegistrationResponse":
        return self

    def __exit__(self, *_args: Any) -> None:
        return None

    def read(self, size: int = -1) -> bytes:
        return self.body if size < 0 else self.body[:size]


def _http_error(body: bytes, code: int = 500) -> HTTPError:
    return HTTPError(
        "https://stat.molit.go.kr/portal/openapi/service/rest/getList.do",
        code,
        "mock error",
        {},
        BytesIO(body),
    )


def test_registration_client_mock_retries_transient_http_and_counts_quota(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = {
        "status_code": "INFO-000",
        "result_data": {"formList": [{"시도명": "서울"}]},
    }
    outcomes: list[Any] = [
        _http_error(b"temporary", code=503),
        _RegistrationResponse(json.dumps(payload, ensure_ascii=False).encode()),
    ]

    def urlopen(*_args: Any, **_kwargs: Any) -> Any:
        outcome = outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(registration_collection, "urlopen", urlopen)
    reservations: list[str] = []
    result, _body = RegistrationApiClient(
        _registration_settings(), max_retries=1
    ).fetch_period("2026-08", lambda: reservations.append("reserved"))

    assert result == payload
    assert reservations == ["reserved", "reserved"]


@pytest.mark.parametrize(
    ("response_body", "error_code"),
    [
        (b"INFO-100", "invalid_api_key"),
        (b"INFO-300", "api_closed"),
    ],
)
def test_registration_client_mock_maps_official_http_status_bodies(
    monkeypatch: pytest.MonkeyPatch,
    response_body: bytes,
    error_code: str,
) -> None:
    monkeypatch.setattr(
        registration_collection,
        "urlopen",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(_http_error(response_body)),
    )

    with pytest.raises(RegistrationError) as exc_info:
        RegistrationApiClient(_registration_settings()).fetch_period(
            "2026-08", lambda: None
        )

    assert exc_info.value.code == error_code


def test_registration_client_mock_treats_official_no_data_as_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        registration_collection,
        "urlopen",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(_http_error(b"INFO-200")),
    )

    payload, body = RegistrationApiClient(_registration_settings()).fetch_period(
        "2026-08", lambda: None
    )

    assert payload == {"status_code": "INFO-200", "result_data": {"formList": []}}
    assert body == b"INFO-200"


@pytest.mark.parametrize(
    ("outcome", "error_code"),
    [
        (URLError("mock connection failure"), "connection_error"),
        (_RegistrationResponse(b"not-json"), "json_schema"),
        (_RegistrationResponse(b"x" * (8 * 1024 * 1024 + 1)), "response_too_large"),
    ],
)
def test_registration_client_mock_rejects_transport_and_payload_failures(
    monkeypatch: pytest.MonkeyPatch,
    outcome: Any,
    error_code: str,
) -> None:
    def urlopen(*_args: Any, **_kwargs: Any) -> Any:
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(registration_collection, "urlopen", urlopen)

    with pytest.raises((RegistrationError, ApiError)) as exc_info:
        RegistrationApiClient(_registration_settings(), max_retries=0).fetch_period(
            "2026-08", lambda: None
        )

    assert exc_info.value.code == error_code


def _faq_document(faq_id: str, content_hash: str) -> dict[str, Any]:
    timestamp = "2026-08-01T00:00:00+00:00"
    return {
        "faq_id": faq_id,
        "question": "Question",
        "answer": "Answer",
        "brand": "Brand A",
        "category": "Purchase",
        "source_url": f"https://source.example.test/{faq_id}",
        "source_updated_at": timestamp,
        "license": "mock-license",
        "attribution": "mock-attribution",
        "content_hash": content_hash,
        "run_id": "mock-run",
        "collected_at": timestamp,
        "created_at": timestamp,
        "updated_at": timestamp,
        "is_active": True,
    }


class _MongoCollection:
    def __init__(self) -> None:
        self.documents: dict[str, dict[str, Any]] = {
            "faq-same": {
                "content_hash": "same",
                "created_at": datetime.now(timezone.utc),
            },
            "faq-changed": {
                "content_hash": "old",
                "created_at": datetime.now(timezone.utc),
            },
        }
        self.indexes: list[tuple[tuple[Any, ...], dict[str, Any]]] = []
        self.updates: list[tuple[Any, Any, bool]] = []

    def create_index(self, *args: Any, **kwargs: Any) -> None:
        self.indexes.append((args, kwargs))

    def find_one(self, query: dict[str, str], _projection: Any) -> Any:
        return self.documents.get(query["faq_id"])

    def update_one(self, query: Any, update: Any, *, upsert: bool) -> None:
        self.updates.append((query, update, upsert))
        self.documents[query["faq_id"]] = {
            "content_hash": update["$set"]["content_hash"],
            "created_at": update["$setOnInsert"]["created_at"],
        }


class _MongoDatabase:
    def __init__(
        self, collection: _MongoCollection, *, valid_validator: bool = True
    ) -> None:
        self.collection = collection
        validator = deepcopy(FAQ_VALIDATOR)
        if not valid_validator:
            validator["$jsonSchema"]["properties"]["updated_at"] = {
                "bsonType": "string"
            }
        self.definition = {
            "options": {
                "validator": validator,
            }
        }

    def __getitem__(self, _name: str) -> _MongoCollection:
        return self.collection

    def list_collection_names(self) -> list[str]:
        return ["faq"]

    def list_collections(self, **_kwargs: Any) -> Any:
        return iter([self.definition])


class _MongoClient:
    def __init__(self, database: _MongoDatabase) -> None:
        self.database = database
        self.closed = False

    def __getitem__(self, _name: str) -> _MongoDatabase:
        return self.database

    def close(self) -> None:
        self.closed = True


def test_mongo_faq_sink_mock_validates_migration_indexes_and_idempotent_upserts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _settings(tmp_path)
    collection = _MongoCollection()
    client = _MongoClient(_MongoDatabase(collection))
    connect_calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

    def mongo_client(*args: Any, **kwargs: Any) -> _MongoClient:
        connect_calls.append((args, kwargs))
        return client

    monkeypatch.setitem(
        sys.modules, "pymongo", SimpleNamespace(MongoClient=mongo_client)
    )
    sink = MongoFaqUpsertSink(settings)

    stats = sink.save(
        [
            _faq_document("faq-new", "new"),
            _faq_document("faq-same", "same"),
            _faq_document("faq-changed", "changed"),
        ]
    )
    rerun = sink.save(
        [
            _faq_document("faq-new", "new"),
            _faq_document("faq-same", "same"),
            _faq_document("faq-changed", "changed"),
        ]
    )
    sink.close()

    assert stats == LoadStats(inserted_count=1, updated_count=1, unchanged_count=1)
    assert rerun == LoadStats(inserted_count=0, updated_count=0, unchanged_count=3)
    assert collection.indexes == [
        (("faq_id",), {"unique": True, "name": "uq_faq_id"}),
        (([("brand", 1), ("category", 1)],), {"name": "ix_faq_brand_category"}),
        (([("updated_at", -1)],), {"name": "ix_faq_updated_at"}),
    ]
    assert len(collection.updates) == 2
    assert all(update[2] is True for update in collection.updates)
    assert connect_calls[0][0] == (settings.mongo_uri,)
    assert connect_calls[0][1]["tz_aware"] is True
    assert client.closed is True


def test_mongo_faq_sink_mock_rejects_incompatible_validator(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _settings(tmp_path)
    client = _MongoClient(_MongoDatabase(_MongoCollection(), valid_validator=False))
    monkeypatch.setitem(
        sys.modules,
        "pymongo",
        SimpleNamespace(MongoClient=lambda *_args, **_kwargs: client),
    )

    with pytest.raises(RuntimeError, match="BSON Date timestamps"):
        MongoFaqUpsertSink(settings)
    assert client.closed is True


class _SqlCursor:
    def __init__(
        self,
        *,
        quota_rowcount: int = 1,
        used_count: int = 1,
        existing_registration: list[tuple[Any, ...]] | None = None,
    ) -> None:
        self.quota_rowcount = quota_rowcount
        self.used_count_value = used_count
        self.existing_registration = existing_registration or []
        self.rowcount = 0
        self.executed: list[tuple[str, Any]] = []
        self.executemany_calls: list[tuple[str, Any]] = []
        self._selected_quota = False
        self._selected_registration = False

    def __enter__(self) -> "_SqlCursor":
        return self

    def __exit__(self, *_args: Any) -> None:
        return None

    def execute(self, query: str, params: Any = None) -> None:
        self.executed.append((query, params))
        if "used_count=used_count+1" in query:
            self.rowcount = self.quota_rowcount
        self._selected_quota = query.startswith("SELECT used_count")
        self._selected_registration = "FROM vehicle_registration_reports" in query

    def executemany(self, query: str, values: Any) -> None:
        batch = list(values)
        self.executemany_calls.append((query, batch))
        if query.startswith("INSERT INTO vehicle_registration_reports"):
            current = {tuple(row[:5]): row for row in self.existing_registration}
            for value in batch:
                key = tuple(value[:5])
                current[key] = (*key, value[12])
            self.existing_registration = list(current.values())

    def fetchone(self) -> Any:
        return (self.used_count_value,) if self._selected_quota else None

    def fetchall(self) -> list[tuple[Any, ...]]:
        return self.existing_registration if self._selected_registration else []


class _SqlConnection:
    def __init__(self, cursor: _SqlCursor) -> None:
        self.cursor_value = cursor
        self.committed_registration = list(cursor.existing_registration)
        self.commits = 0
        self.rollbacks = 0
        self.closed = False

    def cursor(self) -> _SqlCursor:
        self.cursor_value.existing_registration = list(self.committed_registration)
        return self.cursor_value

    def commit(self) -> None:
        self.committed_registration = list(self.cursor_value.existing_registration)
        self.commits += 1

    def rollback(self) -> None:
        self.cursor_value.existing_registration = list(self.committed_registration)
        self.rollbacks += 1

    def close(self) -> None:
        self.closed = True


def _registration_row(*, sigungu: str, content_hash: str) -> dict[str, Any]:
    timestamp = "2026-08-01T00:00:00+00:00"
    return {
        "report_month": "2026-08-01",
        "sido_name": "서울",
        "sigungu_name": sigungu,
        "vehicle_type": "승용",
        "usage_type": "계",
        "quantity": 1,
        "source_name": "molit_car_registration",
        "source_url": "https://stat.molit.go.kr/registration",
        "run_id": "mock-run",
        "collected_at": timestamp,
        "created_at": timestamp,
        "updated_at": timestamp,
        "content_hash": content_hash,
    }


def _install_sql_connection(
    monkeypatch: pytest.MonkeyPatch,
    connection: _SqlConnection,
) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []

    def connect(**kwargs: Any) -> _SqlConnection:
        calls.append(kwargs)
        return connection

    monkeypatch.setitem(sys.modules, "pymysql", SimpleNamespace(connect=connect))
    return calls


def _assert_sql_connect_call(call: dict[str, Any]) -> None:
    assert call == {
        "host": "sql.example.test",
        "port": 3306,
        "user": "mock-user",
        "password": "mock-password",
        "database": "sales_support_db",
        "charset": "utf8mb4",
        "autocommit": False,
    }


def test_sql_quota_ledger_mock_commits_success_and_rolls_back_exhaustion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    success_cursor = _SqlCursor(quota_rowcount=1, used_count=2)
    success_connection = _SqlConnection(success_cursor)
    success_calls = _install_sql_connection(monkeypatch, success_connection)
    ledger = SqlQuotaLedger(_settings(tmp_path))
    ledger._today = lambda: "2026-08-13"  # type: ignore[method-assign]

    ledger.reserve()

    assert success_connection.commits == 1
    assert ledger.used_count == 2
    assert ledger.remaining == 1
    ledger.close()
    assert success_connection.closed is True
    _assert_sql_connect_call(success_calls[0])

    exhausted_connection = _SqlConnection(_SqlCursor(quota_rowcount=0))
    exhausted_calls = _install_sql_connection(monkeypatch, exhausted_connection)
    exhausted = SqlQuotaLedger(_settings(tmp_path))
    exhausted._today = lambda: "2026-08-13"  # type: ignore[method-assign]

    with pytest.raises(QuotaExceeded):
        exhausted.reserve()
    assert exhausted_connection.commits == 0
    assert exhausted_connection.rollbacks == 1
    _assert_sql_connect_call(exhausted_calls[0])


def test_sql_quota_ledger_mock_rolls_back_unexpected_sql_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class FailingCursor(_SqlCursor):
        def execute(self, query: str, params: Any = None) -> None:
            super().execute(query, params)
            if query.startswith("UPDATE api_quota_usage SET quota_status"):
                raise RuntimeError("mock quota SQL failure")

    connection = _SqlConnection(FailingCursor())
    _install_sql_connection(monkeypatch, connection)
    ledger = SqlQuotaLedger(_settings(tmp_path))
    ledger._today = lambda: "2026-08-13"  # type: ignore[method-assign]

    with pytest.raises(RuntimeError, match="quota SQL failure"):
        ledger.reserve()

    assert connection.commits == 0
    assert connection.rollbacks == 1


def test_sql_registration_sink_mock_partitions_insert_update_and_commits(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    changed_key = ("2026-08-01", "서울", "강남구", "승용", "계", "old-hash")
    cursor = _SqlCursor(existing_registration=[changed_key])
    connection = _SqlConnection(cursor)
    connect_calls = _install_sql_connection(monkeypatch, connection)
    sink = SqlRegistrationUpsertSink(_settings(tmp_path))

    stats = sink.save(
        [
            _registration_row(sigungu="강남구", content_hash="new-hash"),
            _registration_row(sigungu="서초구", content_hash="insert-hash"),
        ]
    )

    assert stats == LoadStats(inserted_count=1, updated_count=1, unchanged_count=0)
    assert connection.commits == 1
    assert connection.rollbacks == 0
    assert len(cursor.executemany_calls) == 1
    assert len(cursor.executemany_calls[0][1]) == 2
    query = cursor.executemany_calls[0][0]
    assert "INSERT INTO vehicle_registration_reports" in query
    for column in (
        "report_month",
        "sido_name",
        "sigungu_name",
        "vehicle_type",
        "usage_type",
    ):
        assert column not in query.split("ON DUPLICATE KEY UPDATE", 1)[1]
    _assert_sql_connect_call(connect_calls[0])
    sink.close()
    assert connection.closed is True


def test_sql_registration_sink_mock_unchanged_rerun_skips_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cursor = _SqlCursor()
    connection = _SqlConnection(cursor)
    _install_sql_connection(monkeypatch, connection)
    sink = SqlRegistrationUpsertSink(_settings(tmp_path))
    row = _registration_row(sigungu="강남구", content_hash="same-hash")

    first = sink.save([row])
    second = sink.save([row])

    assert first == LoadStats(inserted_count=1, updated_count=0, unchanged_count=0)
    assert second == LoadStats(inserted_count=0, updated_count=0, unchanged_count=1)
    assert len(cursor.executemany_calls) == 1
    assert len(cursor.executemany_calls[0][1]) == 1
    assert connection.commits == 2
    assert connection.rollbacks == 0


def test_sql_registration_sink_mock_rolls_back_write_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class FailingCursor(_SqlCursor):
        def executemany(self, query: str, values: Any) -> None:
            super().executemany(query, values)
            raise RuntimeError("mock registration write failed")

    cursor = FailingCursor()
    connection = _SqlConnection(cursor)
    _install_sql_connection(monkeypatch, connection)
    sink = SqlRegistrationUpsertSink(_settings(tmp_path))

    with pytest.raises(RuntimeError, match="registration write failed"):
        sink.save([_registration_row(sigungu="강남구", content_hash="new-hash")])

    assert connection.commits == 0
    assert connection.rollbacks == 1
    assert connection.committed_registration == []
    assert cursor.existing_registration == []
