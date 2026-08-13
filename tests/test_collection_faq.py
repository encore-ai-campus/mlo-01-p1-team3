from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

import pytest

from collection import faq as faq_module
from collection.faq import FaqCollector, FaqError, fetch_faq_page, parse_faq_html
from preprocessing.faq import transform_faq_records


def faq_html(next_href: str | None = None, *, faq_id: str = "faq-1") -> bytes:
    next_link = f'<a rel="next" href="{next_href}">next</a>' if next_href else ""
    return f"""
    <html><body>
      <article class="faq-item" data-faq-id="{faq_id}" data-brand="Brand A">
        <div data-field="category">Purchase</div>
        <div data-field="question">Can I <b>buy</b> it?</div>
        <div data-field="answer">Yes, <strong>you can.</strong></div>
        <time data-field="reviewed-at" datetime="2026-08-01"></time>
        <a data-field="source" href="https://source.example/faq/{faq_id}">source</a>
      </article>
      {next_link}
    </body></html>
    """.encode()


@dataclass
class HtmlResponse:
    body: bytes

    headers: dict[str, str] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        self.headers = {"Content-Type": "text/html; charset=utf-8"}

    def __enter__(self) -> "HtmlResponse":
        return self

    def __exit__(self, *args: Any) -> None:
        return None

    def read(self, size: int = -1) -> bytes:
        return self.body if size < 0 else self.body[:size]


def settings(**overrides: Any) -> SimpleNamespace:
    values = {
        "faq_source_url": "https://faq.example.test/faqs",
        "faq_allowed_paths": ("/faqs",),
        "faq_max_pages": 100,
        "faq_interval_seconds": 1.0,
        "timeout_seconds": 5.0,
        "user_agent": "test-agent",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_parse_faq_html_preserves_nested_text_and_hash() -> None:
    result = parse_faq_html(faq_html(), "https://faq.example.test/faqs")

    assert result.records == [
        {
            "faq_id": "faq-1",
            "brand": "Brand A",
            "category": "Purchase",
            "reviewed_at": "2026-08-01",
            "source_url": "https://source.example/faq/faq-1",
            "question": "Can I buy it?",
            "answer": "Yes, you can.",
        }
    ]
    assert len(result.response_sha256) == 64


def test_collection_faq_date_contract_is_accepted_by_preprocessing() -> None:
    page = parse_faq_html(faq_html(), "https://faq.example.test/faqs")
    preprocessing_settings = SimpleNamespace(
        faq_license="educational-sandbox-rewrite",
        faq_attribution="AutoData Lab educational snapshot",
    )

    valid, rejected = transform_faq_records(
        page.records,
        settings=preprocessing_settings,
        run_id="run-1",
        collected_at="2026-08-13T00:00:00+00:00",
    )

    assert rejected == []
    assert len(valid) == 1
    assert valid[0]["source_updated_at"] == "2026-08-01T00:00:00+00:00"


def test_parse_faq_html_rejects_missing_selector_or_required_fields() -> None:
    with pytest.raises(FaqError) as selector_error:
        parse_faq_html(
            b"<html><body><p>not a FAQ</p></body></html>",
            "https://faq.example.test/faqs",
        )
    assert selector_error.value.code == "faq_selector_changed"

    with pytest.raises(FaqError) as schema_error:
        parse_faq_html(faq_html(faq_id=""), "https://faq.example.test/faqs")
    assert schema_error.value.code == "faq_schema"


def test_faq_collector_follows_same_host_allowlisted_next_link() -> None:
    requested: list[str] = []
    pages = {
        "https://faq.example.test/faqs": faq_html("/faqs?page=2"),
        "https://faq.example.test/faqs?page=2": faq_html(faq_id="faq-2"),
    }

    def opener(request: Any, timeout: float) -> HtmlResponse:
        requested.append(request.full_url)
        return HtmlResponse(pages[request.full_url])

    collector = FaqCollector(settings(), opener=opener, sleeper=lambda seconds: None)
    collected = list(collector.iter_pages())

    assert [item.records[0]["faq_id"] for item in collected] == ["faq-1", "faq-2"]
    assert requested == list(pages)


def test_faq_collector_preserves_every_source_record_without_count_truncation() -> None:
    body = (
        b"<html><body>"
        + b"".join(
            faq_html(faq_id=f"faq-{index}")
            .split(b"<body>", 1)[1]
            .split(b"</body>", 1)[0]
            for index in range(24)
        )
        + b"</body></html>"
    )
    collector = FaqCollector(
        settings(faq_max_questions_per_page=10),
        opener=lambda *_args, **_kwargs: HtmlResponse(body),
        sleeper=lambda _seconds: None,
    )

    pages = list(collector.iter_pages())

    assert len(pages) == 1
    assert [row["faq_id"] for row in pages[0].records] == [
        f"faq-{index}" for index in range(24)
    ]


def test_faq_collector_rejects_external_next_and_page_limit() -> None:
    collector = FaqCollector(settings(), opener=lambda *args, **kwargs: None)

    with pytest.raises(FaqError) as origin_error:
        collector._safe_url("https://evil.example.test/faqs")
    assert origin_error.value.code == "source_allowlist"

    pages = {"https://faq.example.test/faqs": faq_html("/faqs?page=2")}

    def opener(request: Any, timeout: float) -> HtmlResponse:
        return HtmlResponse(pages[request.full_url])

    limited = FaqCollector(
        settings(faq_max_pages=1), opener=opener, sleeper=lambda seconds: None
    )
    with pytest.raises(FaqError) as limit_error:
        list(limited.iter_pages())
    assert limit_error.value.code == "faq_page_limit"


@pytest.mark.parametrize("failure", [False, True])
def test_fetch_faq_page_closes_only_internally_owned_client(
    monkeypatch: pytest.MonkeyPatch, failure: bool
) -> None:
    class Client:
        def __init__(self, _settings: Any = None) -> None:
            self.closed = False

        def get_text(self, *_args: Any, **_kwargs: Any) -> str:
            if failure:
                raise RuntimeError("mock FAQ request failed")
            return faq_html().decode()

        def close(self) -> None:
            self.closed = True

    owned = Client()
    monkeypatch.setattr(faq_module, "_settings_from_env", lambda: settings())
    monkeypatch.setattr(faq_module, "ApiClient", lambda _settings: owned)

    if failure:
        with pytest.raises(RuntimeError, match="mock FAQ request failed"):
            fetch_faq_page()
    else:
        assert fetch_faq_page().records[0]["faq_id"] == "faq-1"
    assert owned.closed is True

    injected = Client()
    if failure:
        with pytest.raises(RuntimeError, match="mock FAQ request failed"):
            fetch_faq_page(client=injected)
    else:
        assert fetch_faq_page(client=injected).records[0]["faq_id"] == "faq-1"
    assert injected.closed is False
