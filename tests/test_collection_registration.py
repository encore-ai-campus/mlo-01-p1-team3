from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from urllib.parse import parse_qs, urlsplit

import pytest

import collection.registration as registration
from collection.registration import (
    FixtureRegistrationClient,
    RegistrationApiClient,
    RegistrationError,
    add_month,
    extract_record_list,
    month_label,
    normalize_period,
    response_hash,
)


def test_registration_period_helpers_normalize_month_boundaries() -> None:
    assert normalize_period("2026-08") == "202608"
    assert month_label("202608") == "2026-08"
    assert add_month("202612", 1) == "202701"
    assert add_month("202601", -1) == "202512"

    with pytest.raises(RegistrationError) as exc_info:
        normalize_period("202613")
    assert exc_info.value.code == "invalid_reference_month"


def test_extract_record_list_accepts_documented_envelope_and_no_data() -> None:
    payload = {"status_code": "INFO-000", "result_data": {"formList": [{"region": "Seoul"}]}}
    assert extract_record_list(payload) == [{"region": "Seoul"}]
    assert extract_record_list({"status_code": "INFO-200"}) == []

    with pytest.raises(RegistrationError) as schema_error:
        extract_record_list({"status_code": "INFO-000", "result_data": {}})
    assert schema_error.value.code == "response_schema"


def test_fixture_registration_client_reserves_once_and_selects_period(tmp_path: Path) -> None:
    fixture = tmp_path / "registration.json"
    fixture.write_text(
        json.dumps(
            {
                "pages": [
                    {
                        "period": "202608",
                        "payload": {
                            "status_code": "INFO-000",
                            "result_data": {"formList": [{"region": "Seoul"}]},
                        },
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    calls: list[str] = []
    client = FixtureRegistrationClient(fixture)
    payload, body = client.fetch_period("2026-08", lambda: calls.append("reserved"))

    assert calls == ["reserved"]
    assert payload["result_data"]["formList"] == [{"region": "Seoul"}]
    assert response_hash(body) == response_hash(body)


def test_registration_api_sends_documented_query_and_quota_callback(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = SimpleNamespace(
        registration_api_url="https://stat.molit.go.kr/portal/openapi/service/rest/getList.do",
        registration_api_key="registration-key",
        registration_form_id=5498,
        registration_style_num=2,
        registration_source_page="https://stat.molit.go.kr/",
        user_agent="test-agent",
        timeout_seconds=5.0,
    )
    requests: list[Any] = []

    class Response:
        def __enter__(self) -> "Response":
            return self

        def __exit__(self, *args: Any) -> None:
            return None

        def read(self, size: int = -1) -> bytes:
            return json.dumps(
                {"status_code": "INFO-000", "result_data": {"formList": [{"count": 1}]}}
            ).encode()

    def fake_urlopen(request: Any, timeout: float, context: Any) -> Response:
        requests.append((request, timeout, context))
        return Response()

    monkeypatch.setattr(registration, "urlopen", fake_urlopen)
    client = RegistrationApiClient(settings)
    payload, _ = client.fetch_period("2026-08", lambda: requests.append("reserved"))

    assert payload["result_data"]["formList"] == [{"count": 1}]
    assert requests[0] == "reserved"
    query = parse_qs(urlsplit(requests[1][0].full_url).query)
    assert query == {
        "key": ["registration-key"],
        "form_id": ["5498"],
        "style_num": ["2"],
        "start_dt": ["202608"],
        "end_dt": ["202608"],
    }


def test_registration_api_rejects_unapproved_host_or_missing_key() -> None:
    base = {
        "registration_api_key": "key",
    }

    with pytest.raises(RegistrationError) as host_error:
        RegistrationApiClient(SimpleNamespace(registration_api_url="https://evil.example/", **base))
    assert host_error.value.code == "source_allowlist"

    with pytest.raises(RegistrationError) as key_error:
        RegistrationApiClient(SimpleNamespace(registration_api_url="https://stat.molit.go.kr/", registration_api_key=""))
    assert key_error.value.code == "missing_api_key"
