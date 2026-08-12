"""원격 API와 로컬 JSON에서 원본 데이터를 수집한다."""

import json
import time
from pathlib import Path
from typing import Any

import requests
from bs4 import BeautifulSoup

from config import Settings


# ============================================================================
# COLLECTORS START: API 요청 재시도와 cars/FAQ 수집 기능을 제공한다.
# ============================================================================


def get_api_key(settings: Settings) -> str:
    """차량 API 호출에 사용할 최신 API 키를 조회한다."""
    response = requests.get(settings.public_key_url, timeout=settings.request_timeout_seconds)
    response.raise_for_status()
    return response.json()["data"]["current"]["api_key"]


def request_api(settings: Settings, url: str, api_key: str) -> tuple[dict[str, Any], str]:
    """403 키 갱신, 429/네트워크 오류 재시도를 포함해 JSON API를 호출한다."""
    max_retries = 10
    for retry_count in range(max_retries + 1):
        try:
            response = requests.get(
                url,
                headers={"X-API-Key": api_key},
                timeout=(10, settings.request_timeout_seconds),
            )
            if response.status_code == 403:
                api_key = get_api_key(settings)
                time.sleep(2)
                continue
            if response.status_code == 429:
                retry_after = response.headers.get("Retry-After", "")
                try:
                    delay = int(retry_after)
                except ValueError:
                    delay = min(5 * (retry_count + 1), 60)
                time.sleep(delay)
                continue
            response.raise_for_status()
            return response.json(), api_key
        except (requests.exceptions.ConnectTimeout, requests.exceptions.ReadTimeout, requests.exceptions.ConnectionError):
            if retry_count == max_retries:
                raise
            time.sleep(min(5 * (retry_count + 1), 60))
    raise RuntimeError("API retry limit exceeded")


def collect_car_changes(settings: Settings, after_seq: int) -> list[dict[str, Any]]:
    """마지막 성공 seq 이후의 차량 변경 이벤트를 모두 수집한다."""
    api_key = get_api_key(settings)
    current_seq = after_seq
    events: list[dict[str, Any]] = []
    while True:
        url = f"{settings.changes_url}?after_seq={current_seq}&limit={settings.api_page_size}"
        result, api_key = request_api(settings, url, api_key)
        page_events = result.get("data", [])
        if not page_events:
            break
        events.extend(page_events)
        valid_seqs = [event.get("seq") for event in page_events if isinstance(event.get("seq"), int)]
        if not valid_seqs:
            raise ValueError("changes API response has no valid seq")
        current_seq = max(valid_seqs)
        if not result.get("meta", {}).get("has_more", False):
            break
        time.sleep(1)
    return events


def collect_initial_cars(settings: Settings) -> list[dict[str, Any]]:
    """초기 적재 또는 백필을 위해 cars API 페이지를 순회해 차량 목록을 수집한다."""
    api_key = get_api_key(settings)
    cars: list[dict[str, Any]] = []
    seen_ids: set[Any] = set()
    for page in range(1, settings.api_max_pages + 1):
        url = f"{settings.cars_url}?sort=newest&page={page}&page_size={settings.api_page_size}"
        result, api_key = request_api(settings, url, api_key)
        records = result.get("data", [])
        if not records:
            break
        for record in records:
            car_id = record.get("id")
            if car_id not in seen_ids:
                cars.append(record)
                seen_ids.add(car_id)
        time.sleep(1)
    return cars


def collect_faqs(settings: Settings) -> list[dict[str, Any]]:
    """FAQ HTML 페이지에서 MongoDB용 FAQ 문서를 수집한다."""
    response = requests.get(settings.faqs_url, timeout=settings.request_timeout_seconds)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    records: list[dict[str, Any]] = []
    for item in soup.select("article.faq-item"):
        def text(selector: str, default: str | None = None) -> str | None:
            element = item.select_one(selector)
            return element.get_text(" ", strip=True) if element else default

        records.append({
            "faq_id": item.get("data-faq-id"),
            "brand": text('[data-field="brand"]', item.get("data-brand")),
            "brand_code": item.get("data-brand"),
            "category": text('[data-field="category"]', item.get("data-category")),
            "question": text('[data-field="question"]'),
            "answer": text('[data-field="answer"]'),
            "source_url": item.get("data-source-url"),
            "reviewed_at": item.get("data-reviewed-at"),
            "crawl_url": settings.faqs_url,
        })
    return records


def load_local_json(path: Path) -> list[dict[str, Any]]:
    """전달받은 JSON 파일에서 목록 또는 단일 객체를 읽어 재처리에 사용한다."""
    with path.open("r", encoding="utf-8") as file:
        content = json.load(file)
    if isinstance(content, list):
        return content
    if isinstance(content, dict) and isinstance(content.get("data"), list):
        return content["data"]
    if isinstance(content, dict):
        return [content]
    raise ValueError("local JSON must be an object or an array")


# ============================================================================
# COLLECTORS END: 원본 데이터 수집 기능의 끝.
# ============================================================================
