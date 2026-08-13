"""FAQ HTML source adapter and parser."""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlsplit, urlunsplit
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup

from .api import ApiClient, FetchError


FAQ_PATH = "/faqs"
FAQ_ITEM_SELECTOR = "article.faq-item"
MAX_FAQ_BODY_BYTES = 4 * 1024 * 1024


class FaqError(FetchError):
    """A FAQ source, HTML, or identifier contract error."""


@dataclass(frozen=True)
class FaqPage:
    source_url: str
    records: List[Dict[str, Any]]
    next_url: Optional[str]
    response_sha256: str


def _field_text(card: Any, field: str) -> Optional[str]:
    node = card.select_one(f'[data-field="{field}"]')
    if node is None:
        return None
    value = node.get_text(" ", strip=True)
    return value or None


def _field_attribute(card: Any, field: str, attribute: str) -> Optional[str]:
    node = card.select_one(f'[data-field="{field}"]')
    if node is None:
        return None
    value = node.get(attribute)
    return value.strip() if isinstance(value, str) and value.strip() else None


def parse_faq_html(body: bytes | str, source_url: str) -> FaqPage:
    """Parse live HTML and fixture HTML through exactly the same code path."""

    if not isinstance(source_url, str) or not source_url.strip():
        raise FaqError("FAQ source URL is required", code="source_allowlist")
    raw_body = body.encode("utf-8") if isinstance(body, str) else body
    if not isinstance(raw_body, bytes) or not raw_body:
        raise FaqError("FAQ response body is empty", code="faq_schema")
    if len(raw_body) > MAX_FAQ_BODY_BYTES:
        raise FaqError("FAQ response exceeded 4 MiB", code="faq_response_too_large")
    try:
        text = raw_body.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise FaqError("FAQ response is not UTF-8 HTML", code="faq_encoding") from exc

    try:
        soup = BeautifulSoup(text, "html.parser")
        cards = soup.select(FAQ_ITEM_SELECTOR)
    except Exception as exc:  # pragma: no cover - BeautifulSoup normally raises no parse error
        raise FaqError("FAQ HTML could not be parsed", code="faq_schema") from exc
    if not cards:
        raise FaqError(
            f"FAQ selector changed or returned no items: {FAQ_ITEM_SELECTOR}",
            code="faq_selector_changed",
        )

    records: List[Dict[str, Any]] = []
    for index, card in enumerate(cards):
        source_href = _field_attribute(card, "source", "href")
        reviewed_datetime = _field_attribute(card, "reviewed-at", "datetime")
        record: Dict[str, Any] = {
            "faq_id": card.get("data-faq-id") or _field_text(card, "faq-id"),
            "brand": card.get("data-brand") or _field_text(card, "brand"),
            "category": card.get("data-category") or _field_text(card, "category"),
            "reviewed_at": (
                reviewed_datetime
                or card.get("data-reviewed-at")
                or _field_text(card, "reviewed-at")
            ),
            "source_url": source_href or card.get("data-source-url"),
            "question": _field_text(card, "question"),
            "answer": _field_text(card, "answer"),
        }
        if not record["faq_id"] or not record["question"] or not record["answer"]:
            raise FaqError(
                f"FAQ item identifier/question/answer is missing at index {index}",
                code="faq_schema",
            )
        for field in ("license", "attribution"):
            value = _field_text(card, field)
            if value is not None:
                record[field] = value
        records.append(record)

    next_link = soup.select_one('a[rel~="next"]')
    raw_next_url = next_link.get("href") if next_link is not None else None
    if raw_next_url is not None and (not isinstance(raw_next_url, str) or not raw_next_url.strip()):
        raise FaqError("FAQ next link is invalid", code="faq_schema")
    next_url = urljoin(source_url, raw_next_url) if raw_next_url else None
    return FaqPage(
        source_url=source_url,
        records=records,
        next_url=next_url,
        response_sha256=hashlib.sha256(raw_body).hexdigest(),
    )


class FaqCollector:
    """Sequential, host/path allow-listed FAQ collector."""

    def __init__(
        self,
        settings: Any,
        *,
        opener: Callable[..., Any] = urlopen,
        sleeper: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self.settings = settings
        self.opener = opener
        self.sleeper = sleeper
        self.monotonic = monotonic
        self._next_start: Optional[float] = None
        source_url = str(getattr(settings, "faq_source_url", ""))
        base = urlsplit(source_url)
        if base.scheme not in {"http", "https"} or not base.netloc:
            raise FaqError("FAQ_SOURCE_URL must be an absolute HTTP URL", code="source_allowlist")
        self._base = base
        allowed = tuple(getattr(settings, "faq_allowed_paths", (FAQ_PATH,)))
        if not allowed:
            raise FaqError("FAQ_ALLOWED_PATHS must not be empty", code="source_allowlist")
        self._allowed_paths = {path.rstrip("/") or "/" for path in allowed}
        if base.path.rstrip("/") not in self._allowed_paths:
            raise FaqError("FAQ_SOURCE_URL path is not allow-listed", code="source_allowlist")

    def _safe_url(self, value: str) -> str:
        candidate = urljoin(urlunsplit(self._base), value)
        parsed = urlsplit(candidate)
        if (parsed.scheme, parsed.netloc) != (self._base.scheme, self._base.netloc):
            raise FaqError("FAQ next link points outside configured host", code="source_allowlist")
        if parsed.path.rstrip("/") not in self._allowed_paths:
            raise FaqError("FAQ next link path is not allow-listed", code="source_allowlist")
        return urlunsplit(parsed._replace(fragment=""))

    def _wait_for_next_start(self) -> None:
        now = self.monotonic()
        if self._next_start is not None:
            self.sleeper(max(0.0, self._next_start - now))
        self._next_start = self.monotonic() + float(getattr(self.settings, "faq_interval_seconds", 1.0))

    def _get(self, url: str) -> bytes:
        attempts = 3
        for attempt in range(attempts):
            request = Request(
                url,
                headers={
                    "Accept": "text/html,application/xhtml+xml",
                    "User-Agent": str(getattr(self.settings, "user_agent", "mlo-faq-collector/0.1")),
                },
                method="GET",
            )
            try:
                with self.opener(request, timeout=float(getattr(self.settings, "timeout_seconds", 30.0))) as response:
                    content_type = (response.headers.get("Content-Type") or "").lower()
                    if content_type and "html" not in content_type:
                        raise FaqError("FAQ response Content-Type is not HTML", code="faq_content_type")
                    body = response.read(MAX_FAQ_BODY_BYTES + 1)
                    if len(body) > MAX_FAQ_BODY_BYTES:
                        raise FaqError("FAQ response exceeded 4 MiB", code="faq_response_too_large")
                    return body
            except HTTPError as exc:
                retryable = exc.code in {429, 500, 502, 503, 504}
                if not retryable or attempt + 1 >= attempts:
                    raise FaqError(f"FAQ upstream HTTP {exc.code}", code=f"http_{exc.code}") from exc
                retry_after = 0.0
                if exc.headers and exc.headers.get("Retry-After"):
                    try:
                        retry_after = max(0.0, float(exc.headers["Retry-After"]))
                    except (TypeError, ValueError):
                        retry_after = 0.0
                self.sleeper(max(retry_after, 2.0**attempt))
            except (URLError, TimeoutError) as exc:
                if attempt + 1 >= attempts:
                    raise FaqError("FAQ upstream connection failed", code="connection_error") from exc
                self.sleeper(2.0**attempt)
        raise FaqError("FAQ retry loop exhausted", code="retry_exhausted")

    def iter_pages(self) -> Iterable[FaqPage]:
        next_url: Optional[str] = self._safe_url(str(self.settings.faq_source_url))
        seen: set[str] = set()
        max_pages = int(getattr(self.settings, "faq_max_pages", 2))
        if max_pages <= 0:
            raise ValueError("FAQ_MAX_PAGES must be greater than zero")
        for _ in range(max_pages):
            if next_url is None:
                return
            if next_url in seen:
                raise FaqError("FAQ next link repeated an already requested URL", code="faq_loop")
            seen.add(next_url)
            self._wait_for_next_start()
            page_url = next_url
            page = parse_faq_html(self._get(page_url), page_url)
            max_questions = int(getattr(self.settings, "faq_max_questions_per_page", 10))
            if len(page.records) > max_questions:
                raise FaqError("FAQ question limit exceeded", code="faq_question_limit")
            yield page
            next_url = self._safe_url(page.next_url) if page.next_url else None
        if next_url is not None:
            raise FaqError("FAQ page limit reached before pagination ended", code="faq_page_limit")


def fixture_pages(path: Path) -> Iterable[FaqPage]:
    try:
        body = path.read_bytes()
    except OSError as exc:
        raise FaqError("FAQ fixture could not be read", code="fixture_error") from exc
    yield parse_faq_html(body, "fixture://faqs")


def _settings_from_env() -> Any:
    # Configuration remains owned by common.config; this compatibility helper
    # does not read environment variables directly.
    from common.config import settings_from_env

    return settings_from_env()


def get_faq_page() -> str:
    """Compatibility helper returning the configured page body as text."""

    settings = _settings_from_env()
    collector = FaqCollector(settings)
    body = collector._get(collector._safe_url(settings.faq_source_url))
    return body.decode("utf-8-sig")


def get_text_or_default(item: Any, selector: str, default: Any = None) -> Any:
    element = item.select_one(selector)
    return element.get_text(" ", strip=True) if element else default


def crawl_faqs() -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    for page in FaqCollector(_settings_from_env()).iter_pages():
        records.extend(page.records)
    return records


def fetch_faq_page(*, source_url: Optional[str] = None, client: Optional[ApiClient] = None) -> FaqPage:
    """Compatibility single-page API using ``collection.api`` for transport."""

    settings = _settings_from_env()
    source = source_url or str(settings.faq_source_url)
    http = client or ApiClient(settings)
    body = http.get_text(source, allowed_paths=(urlsplit(source).path,))
    return parse_faq_html(body, source)


def parse_fixture(html: bytes | str, *, source_url: str = "fixture://faqs") -> FaqPage:
    return parse_faq_html(html, source_url)


__all__ = [
    "FAQ_ITEM_SELECTOR",
    "FAQ_PATH",
    "FaqCollector",
    "FaqError",
    "FaqPage",
    "fixture_pages",
    "crawl_faqs",
    "fetch_faq_page",
    "get_faq_page",
    "get_text_or_default",
    "parse_faq_html",
    "parse_fixture",
]
