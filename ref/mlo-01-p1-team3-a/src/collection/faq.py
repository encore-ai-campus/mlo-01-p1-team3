"""FAQ Source adapter: HTML parsing, allow-listing, and bounded collection."""

from __future__ import annotations

import hashlib
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlsplit, urlunsplit
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from common.config import Settings


class FaqError(RuntimeError):
    """A source, response, or FAQ collection contract error."""

    def __init__(self, message: str, code: str = "faq_error", *, retryable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable


@dataclass(frozen=True)
class FaqPage:
    source_url: str
    records: List[Dict[str, Any]]
    next_url: Optional[str]
    response_sha256: str


def _field_text(card: Any, field: str) -> Optional[str]:
    """Read one FAQ field while preserving meaningful nested text."""

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
    raw_body = body.encode("utf-8") if isinstance(body, str) else body
    try:
        text = raw_body.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise FaqError("FAQ response is not UTF-8 HTML", code="faq_encoding") from exc
    try:
        soup = BeautifulSoup(text, "html.parser")
        records: List[Dict[str, Any]] = []
        for card in soup.select("article.faq-item"):
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
            for field in ("license", "attribution"):
                value = _field_text(card, field)
                if value is not None:
                    record[field] = value
            records.append(record)

        next_link = soup.select_one('a[rel~="next"]')
        raw_next_url = next_link.get("href") if next_link is not None else None
    except Exception as exc:
        raise FaqError("FAQ HTML could not be parsed", code="faq_schema") from exc
    if not records:
        raise FaqError("FAQ page contains no article.faq-item cards", code="faq_schema")
    next_url = urljoin(source_url, raw_next_url) if raw_next_url else None
    return FaqPage(
        source_url=source_url,
        records=records,
        next_url=next_url,
        response_sha256=hashlib.sha256(raw_body).hexdigest(),
    )


class FaqCollector:
    """Sequential, allow-listed FAQ HTML collector with bounded retries."""

    def __init__(
        self,
        settings: Settings,
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
        base = urlsplit(settings.faq_source_url)
        if base.scheme not in {"http", "https"} or not base.netloc:
            raise FaqError("FAQ_SOURCE_URL must be an absolute HTTP URL", code="source_allowlist")
        self._base = base

    def _safe_url(self, value: str) -> str:
        parsed = urlsplit(value)
        if (parsed.scheme, parsed.netloc) != (self._base.scheme, self._base.netloc):
            raise FaqError("FAQ next link points outside configured host", code="source_allowlist")
        if parsed.path not in self.settings.faq_allowed_paths:
            raise FaqError("FAQ next link path is not allow-listed", code="source_allowlist")
        return urlunsplit(parsed._replace(fragment=""))

    def _wait_for_next_start(self) -> None:
        now = self.monotonic()
        if self._next_start is not None:
            self.sleeper(max(0.0, self._next_start - now))
        self._next_start = self.monotonic() + self.settings.faq_interval_seconds

    def _get(self, url: str) -> bytes:
        for attempt in range(3):
            request = Request(
                url,
                headers={
                    "Accept": "text/html,application/xhtml+xml",
                    "User-Agent": self.settings.user_agent,
                },
                method="GET",
            )
            try:
                with self.opener(request, timeout=self.settings.timeout_seconds) as response:
                    content_type = (response.headers.get("Content-Type") or "").lower()
                    if content_type and "html" not in content_type:
                        raise FaqError("FAQ response Content-Type is not HTML", code="faq_content_type")
                    body = response.read(4 * 1024 * 1024 + 1)
                    if len(body) > 4 * 1024 * 1024:
                        raise FaqError("FAQ response exceeded 4 MiB limit", code="faq_response_too_large")
                    return body
            except HTTPError as exc:
                retryable = exc.code in {429, 500, 502, 503, 504}
                if not retryable or attempt == 2:
                    raise FaqError(f"FAQ upstream HTTP {exc.code}", code=f"http_{exc.code}") from exc
                retry_after = 0.0
                if exc.headers and exc.headers.get("Retry-After"):
                    try:
                        retry_after = max(0.0, float(exc.headers["Retry-After"]))
                    except ValueError:
                        retry_after = 0.0
                self.sleeper(max(retry_after, 2.0**attempt))
            except (URLError, TimeoutError) as exc:
                if attempt == 2:
                    raise FaqError("FAQ upstream connection failed", code="connection_error") from exc
                self.sleeper(2.0**attempt)
        raise FaqError("FAQ retry loop exhausted", code="retry_exhausted")

    def iter_pages(self) -> Iterable[FaqPage]:
        next_url: Optional[str] = self._safe_url(self.settings.faq_source_url)
        for _ in range(1, self.settings.faq_max_pages + 1):
            if next_url is None:
                return
            self._wait_for_next_start()
            page_url = next_url
            page = parse_faq_html(self._get(page_url), page_url)
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
