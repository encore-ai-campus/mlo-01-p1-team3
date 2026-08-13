from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from common.contracts import LoadStats
from collection.usedcar import FetchError
from loading.registration import QuotaExceeded
from pipelines import registration, usedcar
from src import main as entrypoint


def _faq_fixture(path: Path) -> Path:
    path.write_text(
        """
        <html><body>
          <article class="faq-item" data-faq-id="faq-1" data-brand="Brand A">
            <div data-field="category">Purchase</div>
            <div data-field="question">Can I buy it?</div>
            <div data-field="answer">Yes.</div>
            <time data-field="reviewed-at" datetime="2026-08-01"></time>
            <a data-field="source" href="https://source.example/faq-1">source</a>
          </article>
        </body></html>
        """,
        encoding="utf-8",
    )
    return path


def _registration_fixture(path: Path) -> Path:
    path.write_text(
        json.dumps(
            {
                "status_code": "INFO-000",
                "result_data": {
                    "formList": [
                        {
                            "date": "202606",
                            "시도명": "서울",
                            "시군구": "강남구",
                            "승용>계": 1,
                        }
                    ]
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return path


def _registration_settings(tmp_path: Path, *, quota: int = 3000) -> Any:
    return SimpleNamespace(
        output_dir=tmp_path,
        log_path=tmp_path / "jsonl",
        registration_state_path=tmp_path / "registration_state.json",
        registration_daily_quota=quota,
        time_zone="Asia/Seoul",
        registration_form_id=5498,
        registration_style_num=2,
        registration_api_url="https://stat.molit.go.kr/portal/openapi/service/rest/getList.do",
        registration_source_page="https://stat.molit.go.kr/portal/cate/statView.do?hRsId=58&hFormId=5498",
        registration_api_key=None,
        user_agent="pipeline-test/1.0",
        timeout_seconds=1.0,
    )


def test_main_is_canonical_faq_entrypoint(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    fixture = _faq_fixture(tmp_path / "faq.html")

    exit_code = entrypoint.main(
        [
            "--pipeline",
            "faq",
            "--profile",
            "fixture",
            "--fixture",
            str(fixture),
            "--output-dir",
            str(tmp_path / "output"),
            "--once",
        ]
    )

    captured = capsys.readouterr()
    result = json.loads(captured.out)
    assert exit_code == 0
    assert result["status"] == "OK"
    assert result["pipeline"] == "faq"
    assert result["results"]["faq"]["valid_count"] == 1
    assert result["results"]["faq"]["checkpoint_path"] is None


def test_registration_dry_run_does_not_persist_quota(tmp_path: Path) -> None:
    fixture = _registration_fixture(tmp_path / "registration.json")
    settings = _registration_settings(tmp_path)

    result = registration.run_once(
        settings=settings,
        fixture=fixture,
        period="2026-06",
        dry_run=True,
        run_id="dry-run-registration",
    )

    assert result["status"] == "OK"
    assert result["api_calls"] == 1
    assert result["quota_used"] == 1
    assert not settings.registration_state_path.exists()
    assert not (settings.output_dir / "vehicle_registration_reports.jsonl").exists()


def test_registration_quota_exhaustion_is_not_reported_as_success(tmp_path: Path) -> None:
    fixture = _registration_fixture(tmp_path / "registration.json")
    settings = _registration_settings(tmp_path, quota=1)

    registration.run_once(settings=settings, fixture=fixture, period="2026-06")

    with pytest.raises(QuotaExceeded):
        registration.run_once(settings=settings, fixture=fixture, period="2026-06")


def test_usedcar_rejects_dataset_epoch_change_between_pages(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pages = [
        SimpleNamespace(
            records=[{"id": 1}],
            meta={"dataset_epoch": "epoch-a", "high_water_seq": 1, "until_id": 1},
            next_url=None,
        ),
        SimpleNamespace(
            records=[{"id": 2}],
            meta={"dataset_epoch": "epoch-b", "high_water_seq": 2, "until_id": 2},
            next_url=None,
        ),
    ]

    class FakeFetcher:
        def iter_initial(self, limit: int, max_batches: int) -> Any:
            yield from pages

    class FakeSink:
        def save(self, rows: Any, **kwargs: Any) -> LoadStats:
            return LoadStats(inserted_count=len(rows))

        def close(self) -> None:
            return None

    monkeypatch.setattr(usedcar, "load_fetcher", lambda settings, fixture: FakeFetcher())
    monkeypatch.setattr(usedcar, "sink_for", lambda settings, sink_name: FakeSink())
    monkeypatch.setattr(
        usedcar,
        "transform_records",
        lambda records, **kwargs: ([{"listing": {"listing_id": str(records[0]["id"])}}], []),
    )
    settings = SimpleNamespace(
        state_path=tmp_path / "usedcar_checkpoint.json",
        log_path=tmp_path / "jsonl",
        batch_size=500,
        max_batches=2,
    )

    with pytest.raises(FetchError) as error:
        usedcar.run_once(settings=settings, mode="initial", sink_name="json")

    assert error.value.code == "dataset_epoch_changed"
    checkpoint = json.loads(settings.state_path.read_text(encoding="utf-8"))
    assert checkpoint["dataset_epoch"] == "epoch-a"
    assert checkpoint["after_seq"] == 1
