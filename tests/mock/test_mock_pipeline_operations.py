from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from uuid import UUID

import pytest

from collection.faq import FaqError
from collection.registration import RegistrationError
from collection.usedcar import FetchError
from common.config import Settings
from common.contracts import LoadStats
from pipelines import faq, registration, usedcar
from preprocessing.faq import FaqPreprocessError
from preprocessing.registration import RegistrationPreprocessError
from preprocessing.usedcar import PreprocessError
from src import main as entrypoint


def _settings(tmp_path: Path) -> Settings:
    return Settings.from_env(
        {
            "USED_CAR_BASE_URL": "https://cars.example.test",
            "USED_CAR_API_KEY": "mock-key",
            "OUTPUT_DIR": str(tmp_path),
            "USED_CAR_STATE_PATH": str(tmp_path / "usedcar_checkpoint.json"),
            "LOG_PATH": str(tmp_path / "events.jsonl"),
            "USED_CAR_BATCH_SIZE": "500",
            "USED_CAR_INITIAL_TARGET": "500",
            "USED_CAR_MAX_BATCHES": "2",
            "USED_CAR_INTERVAL_SECONDS": "1",
            "FAQ_SOURCE_URL": "https://faq.example.test/faqs",
            "FAQ_ALLOWED_PATHS": "/faqs",
            "FAQ_INTERVAL_SECONDS": "1",
            "FAQ_MAX_PAGES": "2",
            "FAQ_MAX_QUESTIONS_PER_PAGE": "10",
            "FAQ_LICENSE": "mock-license",
            "FAQ_ATTRIBUTION": "mock-attribution",
            "FAQ_STATE_PATH": str(tmp_path / "faq_checkpoint.json"),
            "REGISTRATION_API_URL": (
                "https://stat.molit.go.kr/portal/openapi/service/rest/getList.do"
            ),
            "REGISTRATION_API_KEY": "mock-registration-key",
            "REGISTRATION_START_PERIOD": "2026-08",
            "REGISTRATION_STATE_PATH": str(tmp_path / "registration_state.json"),
            "SQL_HOST": "sql.example.test",
            "SQL_USER": "mock-user",
            "SQL_PASSWORD": "mock-password",
            "MONGODB_URI": "mongodb://mock-user:mock-password@mongo.example.test:27017/",
        },
        dotenv_path=tmp_path / "missing.env",
    )


def _events(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _faq_record(*, faq_id: str = "faq-1", answer: str = "Yes.") -> dict[str, Any]:
    return {
        "faq_id": faq_id,
        "question": "Can I buy it?",
        "answer": answer,
        "brand": "Brand A",
        "category": "Purchase",
        "source_url": f"https://source.example.test/faqs/{faq_id}",
        "reviewed_at": "2026-08-01",
    }


def _faq_page(records: list[dict[str, Any]], *, digest: str = "a" * 64) -> Any:
    return SimpleNamespace(records=records, response_sha256=digest, next_url=None)


def _usedcar_page(
    records: list[dict[str, Any]],
    *,
    sequence: int | None,
    until_id: int = 1,
    dataset_epoch: str = "epoch-1",
    until_seq: int | None = None,
) -> Any:
    meta: dict[str, Any] = {"until_id": until_id, "dataset_epoch": dataset_epoch}
    if sequence is not None:
        meta["high_water_seq"] = sequence
    if until_seq is not None:
        meta["until_seq"] = until_seq
    return SimpleNamespace(records=records, meta=meta, next_url=None)


class _InitialWatermarkFetcher:
    watermark_sequence: int | None = 1
    watermark_epoch = "epoch-1"

    def incremental_watermark(self) -> dict[str, Any]:
        if self.watermark_sequence is None:
            raise FetchError(
                "mock source has no sequence watermark",
                code="incremental_contract_missing",
            )
        return {
            "high_water_seq": self.watermark_sequence,
            "dataset_epoch": self.watermark_epoch,
        }


def _registration_payload(*records: dict[str, Any]) -> dict[str, Any]:
    return {
        "status_code": "INFO-000",
        "result_data": {"formList": list(records)},
    }


class _Sink:
    def __init__(
        self, stats: LoadStats | None = None, error: Exception | None = None
    ) -> None:
        self.stats = stats or LoadStats()
        self.error = error
        self.calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []
        self.closed = False

    def save(self, *args: Any, **kwargs: Any) -> LoadStats:
        self.calls.append((args, kwargs))
        if self.error is not None:
            raise self.error
        return self.stats

    def close(self) -> None:
        self.closed = True


class _UsedCarSink(_Sink):
    def __init__(
        self,
        *,
        checkpoint: dict[str, Any] | None = None,
        stats: LoadStats | None = None,
        error: Exception | None = None,
    ) -> None:
        super().__init__(stats=stats, error=error)
        self.checkpoint = checkpoint or {}
        self.load_checkpoint_calls = 0

    def load_checkpoint(self) -> dict[str, Any]:
        self.load_checkpoint_calls += 1
        return dict(self.checkpoint)


class _Quota:
    def __init__(self, limit: int = 3, used: int = 0) -> None:
        self.limit = limit
        self.used = used
        self.closed = False

    def reserve(self) -> None:
        if self.used >= self.limit:
            raise registration.QuotaExceeded()
        self.used += 1

    @property
    def used_count(self) -> int:
        return self.used

    @property
    def remaining(self) -> int:
        return max(0, self.limit - self.used)

    def close(self) -> None:
        self.closed = True


def test_faq_mock_pipeline_covers_rejections_mongo_load_and_close(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _settings(tmp_path)
    page = _faq_page([_faq_record(), _faq_record(faq_id="faq-2", answer="")])
    sink = _Sink(LoadStats(inserted_count=1))

    class Collector:
        def __init__(self, actual_settings: Settings) -> None:
            assert actual_settings is settings

        def iter_pages(self) -> Any:
            yield page

    monkeypatch.setattr(faq, "FaqCollector", Collector)
    monkeypatch.setattr(faq, "MongoFaqUpsertSink", lambda actual: sink)

    result = faq.run_once(
        settings=settings,
        sink_name="mongo",
        run_id="faq-mock-run",
    )

    assert result == {
        "status": "OK",
        "run_id": "faq-mock-run",
        "mode": "bounded",
        "pages": 1,
        "collected_count": 2,
        "preprocessed_count": 2,
        "valid_count": 1,
        "rejected_count": 1,
        "inserted_count": 1,
        "updated_count": 0,
        "unchanged_count": 0,
        "dry_run": False,
        "checkpoint_path": None,
    }
    assert len(sink.calls) == 1
    assert [row["faq_id"] for row in sink.calls[0][0][0]] == ["faq-1"]
    assert sink.closed is True
    assert [event["event_name"] for event in _events(settings.log_path)] == [
        "run_started",
        "collection_completed",
        "preprocess_completed",
        "validation_completed",
        "records_rejected",
        "run_succeeded",
    ]
    rejection = next(
        event
        for event in _events(settings.log_path)
        if event["event_name"] == "records_rejected"
    )
    assert rejection["level"] == "ERROR"
    assert rejection["discard_policy"] == "log_only"
    assert rejection["discarded_count"] == 1


def test_faq_mock_all_rejected_stops_before_sink_and_logs_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _settings(tmp_path)
    monkeypatch.setattr(
        faq,
        "FaqCollector",
        lambda _settings: SimpleNamespace(
            iter_pages=lambda: iter([_faq_page([_faq_record(answer="")])])
        ),
    )
    monkeypatch.setattr(
        faq,
        "MongoFaqUpsertSink",
        lambda _settings: pytest.fail("all-rejected FAQ batch constructed a sink"),
    )

    with pytest.raises(FaqPreprocessError) as exc_info:
        faq.run_once(settings=settings, sink_name="mongo")

    assert exc_info.value.code == "all_records_rejected"
    assert not (settings.output_dir / "faq.jsonl").exists()
    events = _events(settings.log_path)
    assert events[-2]["event_name"] == "records_rejected"
    assert events[-2]["level"] == "ERROR"
    assert events[-1]["error_code"] == "all_records_rejected"
    assert events[-1]["stage_name"] == "Validate"


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("faq_max_pages", 3, "FAQ_MAX_PAGES"),
        ("faq_interval_seconds", 0.5, "FAQ_INTERVAL_SECONDS"),
    ],
)
def test_faq_mock_pipeline_rejects_unsafe_operating_limits(
    tmp_path: Path, field: str, value: Any, message: str
) -> None:
    settings = replace(_settings(tmp_path), **{field: value})

    with pytest.raises(ValueError, match=message):
        faq.run_once(settings=settings)

    assert not settings.log_path.exists()


def test_faq_mock_pipeline_logs_collection_and_preprocess_failures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _settings(tmp_path)

    class FailingCollector:
        def __init__(self, _settings: Settings) -> None:
            pass

        def iter_pages(self) -> Any:
            raise FaqError("mock collection failed", code="mock_collection")
            yield

    monkeypatch.setattr(faq, "FaqCollector", FailingCollector)
    with pytest.raises(FaqError, match="mock collection failed"):
        faq.run_once(settings=settings, run_id="faq-collection-failure")

    collection_events = _events(settings.log_path)
    assert collection_events[-1]["event_name"] == "collection_failed"
    assert collection_events[-1]["error_code"] == "mock_collection"

    settings.log_path.unlink()
    monkeypatch.setattr(
        faq,
        "FaqCollector",
        lambda _settings: SimpleNamespace(
            iter_pages=lambda: iter([_faq_page([_faq_record()])])
        ),
    )

    def fail_preprocess(*_args: Any, **_kwargs: Any) -> Any:
        raise FaqPreprocessError("mock preprocess failed", code="mock_preprocess")

    monkeypatch.setattr(faq, "transform_faq_records", fail_preprocess)
    with pytest.raises(FaqPreprocessError, match="mock preprocess failed"):
        faq.run_once(settings=settings, run_id="faq-preprocess-failure")

    preprocess_events = _events(settings.log_path)
    assert preprocess_events[-1]["event_name"] == "preprocess_failed"
    assert preprocess_events[-1]["error_code"] == "mock_preprocess"


def test_faq_mock_pipeline_load_failure_closes_sink_and_does_not_report_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _settings(tmp_path)
    sink = _Sink(error=RuntimeError("mock MongoDB write failed"))
    monkeypatch.setattr(
        faq,
        "FaqCollector",
        lambda _settings: SimpleNamespace(
            iter_pages=lambda: iter([_faq_page([_faq_record()])])
        ),
    )
    monkeypatch.setattr(faq, "MongoFaqUpsertSink", lambda _settings: sink)

    with pytest.raises(RuntimeError, match="mock MongoDB write failed"):
        faq.run_once(settings=settings, sink_name="mongo", run_id="faq-load-failure")

    assert sink.closed is True
    assert _events(settings.log_path)[-1]["event_name"] == "run_failed"
    assert not any(
        event["event_name"] == "run_succeeded" for event in _events(settings.log_path)
    )


def test_faq_mock_dry_run_never_constructs_persistent_sink(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _settings(tmp_path)
    monkeypatch.setattr(
        faq,
        "FaqCollector",
        lambda _settings: SimpleNamespace(
            iter_pages=lambda: iter([_faq_page([_faq_record()])])
        ),
    )
    monkeypatch.setattr(
        faq,
        "MongoFaqUpsertSink",
        lambda _settings: pytest.fail("dry-run constructed a MongoDB sink"),
    )

    result = faq.run_once(settings=settings, sink_name="mongo", dry_run=True)

    assert result["dry_run"] is True
    assert result["inserted_count"] == 0
    assert result["valid_count"] == 1


def test_usedcar_mock_sql_auto_incremental_uses_sql_checkpoint_transactionally(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _settings(tmp_path)
    pages = [_usedcar_page([{"id": 101}], sequence=12, until_id=101)]
    fetch_calls: list[tuple[str, int, int, int]] = []

    class Fetcher(_InitialWatermarkFetcher):
        watermark_sequence = 2

        def iter_initial(self, limit: int, max_batches: int) -> Any:
            pytest.fail("auto mode ignored the initialized SQL checkpoint")

        def iter_incremental(self, after_seq: int, limit: int, max_batches: int) -> Any:
            fetch_calls.append(("incremental", after_seq, limit, max_batches))
            yield from pages

    sink = _UsedCarSink(
        checkpoint={"initialized": True, "after_seq": 11, "dataset_epoch": "epoch-1"},
        stats=LoadStats(inserted_count=1),
    )
    monkeypatch.setattr(usedcar, "load_fetcher", lambda _settings, _fixture: Fetcher())
    monkeypatch.setattr(usedcar, "sink_for", lambda _settings, _name: sink)

    result = usedcar.run_once(
        settings=settings,
        mode="auto",
        sink_name="sql",
        run_id="usedcar-mock-run",
    )

    assert fetch_calls == [("incremental", 11, 500, 2)]
    assert result["mode"] == "incremental"
    assert result["inserted_count"] == 1
    assert sink.load_checkpoint_calls == 1
    assert len(sink.calls) == 1
    rows = sink.calls[0][0][0]
    save_kwargs = sink.calls[0][1]
    assert rows[0]["listing"]["listing_id"] == "101"
    assert save_kwargs["checkpoint"]["after_seq"] == 12
    assert save_kwargs["checkpoint"]["dataset_epoch"] == "epoch-1"
    assert UUID(save_kwargs["run_id"])
    assert save_kwargs["run_id"] != "usedcar-mock-run"
    started_at = datetime.fromisoformat(save_kwargs["started_at"])
    assert started_at.tzinfo is not None
    assert (
        json.loads(settings.state_path.read_text(encoding="utf-8"))["after_seq"] == 12
    )
    assert sink.closed is True
    assert _events(settings.log_path)[-1]["event_name"] == "run_succeeded"


def test_usedcar_mock_dry_run_tracks_rejections_without_sink_or_checkpoint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _settings(tmp_path)
    page = _usedcar_page([{"id": 1}, {"title": "missing id"}], sequence=2, until_id=2)

    class Fetcher(_InitialWatermarkFetcher):
        def iter_initial(self, limit: int, max_batches: int) -> Any:
            yield page

    monkeypatch.setattr(usedcar, "load_fetcher", lambda _settings, _fixture: Fetcher())
    monkeypatch.setattr(
        usedcar,
        "sink_for",
        lambda _settings, _name: pytest.fail("dry-run constructed a persistent sink"),
    )

    result = usedcar.run_once(
        settings=settings,
        mode="initial",
        sink_name="json",
        dry_run=True,
        run_id="usedcar-dry-run",
    )

    assert result["collected_count"] == 2
    assert result["valid_count"] == 1
    assert result["rejected_count"] == 1
    assert result["inserted_count"] == 0
    assert not settings.state_path.exists()
    names = [event["event_name"] for event in _events(settings.log_path)]
    assert "records_rejected" in names
    assert "load_skipped" in names
    assert names[-1] == "run_succeeded"
    rejection = next(
        event
        for event in _events(settings.log_path)
        if event["event_name"] == "records_rejected"
    )
    assert rejection["level"] == "ERROR"
    assert rejection["discard_policy"] == "log_only"


def test_usedcar_mock_partial_reject_commits_valid_rows_and_advances_checkpoint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _settings(tmp_path)
    sink = _UsedCarSink(stats=LoadStats(inserted_count=1))

    class Fetcher(_InitialWatermarkFetcher):
        watermark_sequence = 2

        def iter_initial(self, limit: int, max_batches: int) -> Any:
            yield _usedcar_page(
                [{"id": 1}, {"title": "missing id"}],
                sequence=2,
                until_id=2,
            )

    monkeypatch.setattr(usedcar, "load_fetcher", lambda *_args: Fetcher())
    monkeypatch.setattr(usedcar, "sink_for", lambda *_args: sink)

    result = usedcar.run_once(settings=settings, mode="initial", sink_name="sql")

    assert result["status"] == "OK"
    assert result["valid_count"] == 1
    assert result["rejected_count"] == 1
    assert len(sink.calls) == 2
    assert len(sink.calls[0][0][0]) == 1
    assert sink.calls[0][1]["checkpoint"] is None
    assert sink.calls[1][0][0] == ()
    assert sink.calls[1][1]["checkpoint"]["after_seq"] == 2
    assert sink.calls[1][1]["record_stats"] == LoadStats(inserted_count=1)
    assert sink.calls[1][1]["run_counts"]["api_calls"] == 2
    checkpoint = json.loads(settings.state_path.read_text(encoding="utf-8"))
    assert checkpoint["after_seq"] == 2


def test_usedcar_mock_all_rejected_keeps_checkpoint_and_skips_save(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _settings(tmp_path)
    existing = {
        "initialized": True,
        "after_seq": 11,
        "dataset_epoch": "epoch-1",
    }
    settings.state_path.write_text(json.dumps(existing), encoding="utf-8")
    sink = _UsedCarSink(checkpoint=existing)

    class Fetcher(_InitialWatermarkFetcher):
        def iter_incremental(self, after_seq: int, limit: int, max_batches: int) -> Any:
            assert after_seq == 11
            yield _usedcar_page([{"seq": 12}], sequence=12, until_id=12)

    monkeypatch.setattr(usedcar, "load_fetcher", lambda *_args: Fetcher())
    monkeypatch.setattr(usedcar, "sink_for", lambda *_args: sink)

    with pytest.raises(PreprocessError) as exc_info:
        usedcar.run_once(settings=settings, mode="auto", sink_name="sql")

    assert exc_info.value.code == "all_records_rejected"
    assert sink.calls == []
    assert sink.closed is True
    assert json.loads(settings.state_path.read_text(encoding="utf-8")) == existing
    events = _events(settings.log_path)
    assert events[-2]["event_name"] == "records_rejected"
    assert events[-1]["error_code"] == "all_records_rejected"
    assert events[-1]["stage_name"] == "Validate"


def test_usedcar_mock_empty_incremental_steady_state_keeps_checkpoint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _settings(tmp_path)
    existing = {
        "initialized": True,
        "after_seq": 11,
        "dataset_epoch": "epoch-1",
    }
    settings.state_path.write_text(json.dumps(existing), encoding="utf-8")
    sink = _UsedCarSink(checkpoint=existing, stats=LoadStats())

    class Fetcher(_InitialWatermarkFetcher):
        closed = False

        def iter_incremental(self, after_seq: int, limit: int, max_batches: int) -> Any:
            assert after_seq == 11
            yield _usedcar_page(
                [],
                sequence=None,
                until_id=0,
                until_seq=11,
            )

        def close(self) -> None:
            self.closed = True

    fetcher = Fetcher()
    monkeypatch.setattr(usedcar, "load_fetcher", lambda *_args: fetcher)
    monkeypatch.setattr(usedcar, "sink_for", lambda *_args: sink)

    result = usedcar.run_once(settings=settings, mode="auto", sink_name="sql")

    assert result["status"] == "OK"
    assert result["collected_count"] == 0
    assert result["inserted_count"] == result["updated_count"] == 0
    assert sink.calls[0][1]["checkpoint"]["after_seq"] == 11
    assert (
        json.loads(settings.state_path.read_text(encoding="utf-8"))["after_seq"] == 11
    )
    assert fetcher.closed is True


def test_usedcar_mock_checkpoint_regression_fails_before_save(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _settings(tmp_path)
    existing = {
        "initialized": True,
        "after_seq": 11,
        "dataset_epoch": "epoch-1",
    }
    settings.state_path.write_text(json.dumps(existing), encoding="utf-8")
    sink = _UsedCarSink(checkpoint=existing)

    class Fetcher(_InitialWatermarkFetcher):
        def iter_incremental(self, after_seq: int, limit: int, max_batches: int) -> Any:
            assert after_seq == 11
            yield _usedcar_page([{"id": 10}], sequence=10, until_id=10)

    monkeypatch.setattr(usedcar, "load_fetcher", lambda *_args: Fetcher())
    monkeypatch.setattr(usedcar, "sink_for", lambda *_args: sink)

    with pytest.raises(FetchError) as exc_info:
        usedcar.run_once(settings=settings, mode="auto", sink_name="sql")

    assert exc_info.value.code == "checkpoint_regression"
    assert sink.calls == []
    assert sink.closed is True
    assert json.loads(settings.state_path.read_text(encoding="utf-8")) == existing


def test_usedcar_mock_explicit_initial_cannot_regress_committed_checkpoint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _settings(tmp_path)
    existing = {
        "initialized": True,
        "after_seq": 11,
        "dataset_epoch": "epoch-1",
    }
    settings.state_path.write_text(json.dumps(existing), encoding="utf-8")
    sink = _UsedCarSink(checkpoint=existing)

    class Fetcher(_InitialWatermarkFetcher):
        def iter_initial(self, limit: int, max_batches: int) -> Any:
            yield _usedcar_page([{"id": 10}], sequence=10, until_id=10)

    monkeypatch.setattr(usedcar, "load_fetcher", lambda *_args: Fetcher())
    monkeypatch.setattr(usedcar, "sink_for", lambda *_args: sink)

    with pytest.raises(FetchError) as exc_info:
        usedcar.run_once(
            settings=settings,
            mode="initial",
            sink_name="sql",
        )

    assert exc_info.value.code == "checkpoint_regression"
    assert sink.calls == []
    assert json.loads(settings.state_path.read_text(encoding="utf-8")) == existing


def test_usedcar_mock_empty_batch_is_successful_and_advances_source_checkpoint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _settings(tmp_path)
    sink = _UsedCarSink(stats=LoadStats())

    class Fetcher(_InitialWatermarkFetcher):
        def iter_initial(self, limit: int, max_batches: int) -> Any:
            yield _usedcar_page([], sequence=1, until_id=0)

    monkeypatch.setattr(usedcar, "load_fetcher", lambda *_args: Fetcher())
    monkeypatch.setattr(usedcar, "sink_for", lambda *_args: sink)

    result = usedcar.run_once(settings=settings, mode="initial", sink_name="sql")

    assert result["status"] == "OK"
    assert result["collected_count"] == 0
    assert result["valid_count"] == 0
    assert result["rejected_count"] == 0
    assert len(sink.calls) == 2
    assert sink.calls[0][0][0] == ()
    assert sink.calls[0][1]["checkpoint"] is None
    assert sink.calls[1][0][0] == ()
    assert sink.calls[1][1]["checkpoint"]["after_seq"] == 1
    assert json.loads(settings.state_path.read_text(encoding="utf-8"))["after_seq"] == 1


def test_usedcar_mock_missing_incremental_contract_fails_without_checkpoint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _settings(tmp_path)
    sink = _UsedCarSink(stats=LoadStats(inserted_count=1))

    class Fetcher(_InitialWatermarkFetcher):
        watermark_sequence = None

        def iter_initial(self, limit: int, max_batches: int) -> Any:
            yield _usedcar_page([{"id": 1}], sequence=None)

    monkeypatch.setattr(usedcar, "load_fetcher", lambda _settings, _fixture: Fetcher())
    monkeypatch.setattr(usedcar, "sink_for", lambda _settings, _name: sink)

    with pytest.raises(FetchError) as exc_info:
        usedcar.run_once(settings=settings, mode="initial", run_id="missing-contract")

    assert exc_info.value.code == "incremental_contract_missing"
    assert sink.calls == []
    assert not settings.state_path.exists()
    assert sink.closed is True
    assert (
        _events(settings.log_path)[-1]["error_code"] == "incremental_contract_missing"
    )


def test_usedcar_mock_load_failure_does_not_advance_checkpoint_and_closes_sink(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _settings(tmp_path)
    sink = _UsedCarSink(error=RuntimeError("mock SQL write failed"))

    class Fetcher(_InitialWatermarkFetcher):
        def iter_initial(self, limit: int, max_batches: int) -> Any:
            yield _usedcar_page([{"id": 1}], sequence=1)

    monkeypatch.setattr(usedcar, "load_fetcher", lambda _settings, _fixture: Fetcher())
    monkeypatch.setattr(usedcar, "sink_for", lambda _settings, _name: sink)

    with pytest.raises(RuntimeError, match="mock SQL write failed"):
        usedcar.run_once(settings=settings, mode="initial", sink_name="sql")

    assert not settings.state_path.exists()
    assert sink.closed is True
    last_event = _events(settings.log_path)[-1]
    assert (last_event["event_name"], last_event["stage_name"]) == (
        "run_failed",
        "Load",
    )


def test_usedcar_mock_initial_finalization_failure_keeps_checkpoint_uncommitted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _settings(tmp_path)

    class FinalizationFailingSink(_UsedCarSink):
        def save(self, *args: Any, **kwargs: Any) -> LoadStats:
            self.calls.append((args, kwargs))
            if len(self.calls) == 2:
                raise RuntimeError("mock checkpoint finalization failed")
            return LoadStats(inserted_count=1)

    sink = FinalizationFailingSink()

    class Fetcher(_InitialWatermarkFetcher):
        watermark_sequence = 7

        def iter_initial(self, limit: int, max_batches: int) -> Any:
            yield _usedcar_page([{"id": 1}], sequence=1, until_id=1)

    monkeypatch.setattr(usedcar, "load_fetcher", lambda *_args: Fetcher())
    monkeypatch.setattr(usedcar, "sink_for", lambda *_args: sink)

    with pytest.raises(RuntimeError, match="checkpoint finalization failed"):
        usedcar.run_once(settings=settings, mode="initial", sink_name="sql")

    assert len(sink.calls) == 2
    assert len(sink.calls[0][0][0]) == 1
    assert sink.calls[0][1]["checkpoint"] is None
    assert sink.calls[1][0][0] == ()
    assert sink.calls[1][1]["checkpoint"]["after_seq"] == 7
    assert not settings.state_path.exists()
    assert sink.closed is True
    last_event = _events(settings.log_path)[-1]
    assert (last_event["event_name"], last_event["stage_name"]) == (
        "run_failed",
        "Load",
    )


def test_usedcar_mock_preprocess_failure_logs_both_stage_and_run_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _settings(tmp_path)
    sink = _UsedCarSink()

    class Fetcher(_InitialWatermarkFetcher):
        def iter_initial(self, limit: int, max_batches: int) -> Any:
            yield _usedcar_page([{"id": 1}], sequence=1)

    def fail_preprocess(*_args: Any, **_kwargs: Any) -> Any:
        raise PreprocessError("mock transform failure", code="mock_preprocess")

    monkeypatch.setattr(usedcar, "load_fetcher", lambda _settings, _fixture: Fetcher())
    monkeypatch.setattr(usedcar, "sink_for", lambda _settings, _name: sink)
    monkeypatch.setattr(usedcar, "transform_records", fail_preprocess)

    with pytest.raises(PreprocessError, match="mock transform failure"):
        usedcar.run_once(settings=settings, mode="initial")

    assert sink.closed is True
    events = _events(settings.log_path)
    assert [event["event_name"] for event in events[-2:]] == [
        "preprocess_failed",
        "run_failed",
    ]
    assert events[-1]["stage_name"] == "Preprocess"


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"sink_name": "mongo"}, "unsupported used-car sink"),
        ({"mode": "continuous"}, "mode must be auto"),
    ],
)
def test_usedcar_mock_rejects_unsupported_operating_contracts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    kwargs: dict[str, Any],
    message: str,
) -> None:
    settings = _settings(tmp_path)
    monkeypatch.setattr(
        usedcar,
        "load_fetcher",
        lambda _settings, _fixture: SimpleNamespace(
            iter_initial=lambda *_args: iter(())
        ),
    )
    monkeypatch.setattr(usedcar, "sink_for", lambda _settings, _name: _UsedCarSink())

    with pytest.raises(ValueError, match=message):
        usedcar.run_once(settings=settings, **kwargs)


def test_registration_mock_sql_pipeline_covers_quota_rejections_state_and_close(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _settings(tmp_path)
    quota = _Quota()
    sink = _Sink(LoadStats(inserted_count=12))
    vehicle_types = ("승용", "승합", "화물", "특수", "총계")
    usage_types = ("관용", "자가용", "영업용", "계")
    payload = _registration_payload(
        {
            "date": "202608",
            "시도명": "서울",
            "시군구": "강남구",
            **{
                f"{vehicle_type}>{usage_type}": 1
                for vehicle_type in vehicle_types
                for usage_type in usage_types
            },
        },
        {"date": "202608", "시도명": "서울", "승용>관용": 2},
    )

    class Client:
        def __init__(self, actual_settings: Settings) -> None:
            assert actual_settings is settings

        def fetch_period(self, period: str, reserve_call: Any) -> tuple[Any, bytes]:
            assert period == "202608"
            reserve_call()
            return payload, json.dumps(payload, ensure_ascii=False).encode()

    monkeypatch.setattr(registration, "RegistrationApiClient", Client)
    monkeypatch.setattr(registration, "SqlQuotaLedger", lambda _settings: quota)
    monkeypatch.setattr(
        registration, "SqlRegistrationUpsertSink", lambda _settings: sink
    )

    result = registration.run_once(
        settings=settings,
        sink_name="sql",
        period="2026-08",
        run_id="registration-mock-run",
    )

    assert result["status"] == "OK"
    assert result["api_calls"] == 1
    assert result["quota_used"] == 1
    assert result["valid_count"] == 12
    assert result["rejected_count"] == 1
    assert result["inserted_count"] == 12
    assert len(sink.calls) == 1
    loaded_rows = sink.calls[0][0][0]
    assert len(loaded_rows) == 12
    assert {(row["vehicle_type"], row["usage_type"]) for row in loaded_rows} == {
        (vehicle_type, usage_type)
        for vehicle_type in vehicle_types[:-1]
        for usage_type in usage_types[:-1]
    }
    state = json.loads(settings.registration_state_path.read_text(encoding="utf-8"))
    assert state["last_success_period"] == "202608"
    assert state["last_run_id"] == "registration-mock-run"
    assert sink.closed is True
    assert quota.closed is True
    names = [event["event_name"] for event in _events(settings.log_path)]
    assert "records_rejected" in names
    assert names[-1] == "run_succeeded"
    rejection = next(
        event
        for event in _events(settings.log_path)
        if event["event_name"] == "records_rejected"
    )
    assert rejection["level"] == "ERROR"
    assert rejection["discard_policy"] == "log_only"


def test_registration_mock_all_rejected_keeps_state_and_skips_save(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _settings(tmp_path)
    existing = {"last_success_period": "202607", "last_run_id": "previous"}
    settings.registration_state_path.write_text(json.dumps(existing), encoding="utf-8")
    quota = _Quota()
    sink = _Sink()
    payload = _registration_payload(
        {"date": "202608", "시도명": "서울", "승용>관용": 2}
    )

    class Client:
        def __init__(self, _settings: Settings) -> None:
            pass

        def fetch_period(self, period: str, reserve_call: Any) -> tuple[Any, bytes]:
            reserve_call()
            return payload, b"all-rejected"

    monkeypatch.setattr(registration, "RegistrationApiClient", Client)
    monkeypatch.setattr(registration, "SqlQuotaLedger", lambda _settings: quota)
    monkeypatch.setattr(
        registration, "SqlRegistrationUpsertSink", lambda _settings: sink
    )

    with pytest.raises(RegistrationPreprocessError) as exc_info:
        registration.run_once(
            settings=settings,
            sink_name="sql",
            period="2026-08",
        )

    assert exc_info.value.code == "all_records_rejected"
    assert sink.calls == []
    assert sink.closed is True
    assert quota.closed is True
    assert quota.used_count == 1
    assert (
        json.loads(settings.registration_state_path.read_text(encoding="utf-8"))
        == existing
    )
    events = _events(settings.log_path)
    assert events[-2]["event_name"] == "records_rejected"
    assert events[-1]["error_code"] == "all_records_rejected"
    assert events[-1]["stage_name"] == "Validate"


def test_registration_mock_json_all_rejected_consumes_quota_but_keeps_success_checkpoint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _settings(tmp_path)
    existing = {
        "last_success_period": "202607",
        "last_run_id": "previous",
    }
    settings.registration_state_path.write_text(json.dumps(existing), encoding="utf-8")
    sink = _Sink()
    payload = _registration_payload(
        {"date": "202608", "시도명": "서울", "승용>관용": 2}
    )

    class Client:
        def __init__(self, _settings: Settings) -> None:
            pass

        def fetch_period(self, period: str, reserve_call: Any) -> tuple[Any, bytes]:
            reserve_call()
            return payload, b"all-rejected-json"

    monkeypatch.setattr(registration, "RegistrationApiClient", Client)
    monkeypatch.setattr(
        registration,
        "JsonlRegistrationUpsertSink",
        lambda _path: sink,
    )

    with pytest.raises(RegistrationPreprocessError) as exc_info:
        registration.run_once(
            settings=settings,
            sink_name="json",
            period="2026-08",
        )

    assert exc_info.value.code == "all_records_rejected"
    assert sink.calls == []
    assert sink.closed is True
    state = json.loads(settings.registration_state_path.read_text(encoding="utf-8"))
    assert state["used_count"] == 1
    assert state["last_success_period"] == "202607"
    assert state["last_run_id"] == "previous"
    assert "updated_at" not in state


def test_registration_mock_sink_close_failure_still_closes_quota_and_never_logs_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _settings(tmp_path)
    quota = _Quota()
    payload = _registration_payload(
        {
            "date": "202608",
            "시도명": "서울",
            "시군구": "강남구",
            "승용>관용": 1,
        }
    )

    class Client:
        def __init__(self, _settings: Settings) -> None:
            pass

        def fetch_period(self, period: str, reserve_call: Any) -> tuple[Any, bytes]:
            reserve_call()
            return payload, b"close-failure"

    class CloseFailingSink(_Sink):
        def close(self) -> None:
            self.closed = True
            raise RuntimeError("mock sink close failure")

    sink = CloseFailingSink(LoadStats(inserted_count=1))
    monkeypatch.setattr(registration, "RegistrationApiClient", Client)
    monkeypatch.setattr(registration, "SqlQuotaLedger", lambda _settings: quota)
    monkeypatch.setattr(
        registration,
        "SqlRegistrationUpsertSink",
        lambda _settings: sink,
    )

    with pytest.raises(RuntimeError, match="sink close failure"):
        registration.run_once(
            settings=settings,
            sink_name="sql",
            period="2026-08",
        )

    assert sink.closed is True
    assert quota.closed is True
    events = _events(settings.log_path)
    assert events[-1]["event_name"] == "run_failed"
    assert events[-1]["error_code"] == "resource_close_failed"
    assert not any(event["event_name"] == "run_succeeded" for event in events)


def test_faq_mock_sink_close_failure_never_logs_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _settings(tmp_path)

    class CloseFailingSink(_Sink):
        def close(self) -> None:
            self.closed = True
            raise RuntimeError("mock FAQ close failure")

    sink = CloseFailingSink(LoadStats(inserted_count=1))
    monkeypatch.setattr(
        faq,
        "FaqCollector",
        lambda _settings: SimpleNamespace(
            iter_pages=lambda: iter([_faq_page([_faq_record()])])
        ),
    )
    monkeypatch.setattr(faq, "MongoFaqUpsertSink", lambda _settings: sink)

    with pytest.raises(RuntimeError, match="FAQ close failure"):
        faq.run_once(settings=settings, sink_name="mongo")

    assert sink.closed is True
    events = _events(settings.log_path)
    assert events[-1]["event_name"] == "run_failed"
    assert events[-1]["error_code"] == "resource_close_failed"
    assert not any(event["event_name"] == "run_succeeded" for event in events)


def test_usedcar_mock_sink_close_failure_never_logs_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _settings(tmp_path)

    class CloseFailingSink(_UsedCarSink):
        def close(self) -> None:
            self.closed = True
            raise RuntimeError("mock used-car close failure")

    sink = CloseFailingSink(stats=LoadStats(inserted_count=1))

    class Fetcher(_InitialWatermarkFetcher):
        def iter_initial(self, limit: int, max_batches: int) -> Any:
            yield _usedcar_page([{"id": 1}], sequence=1)

    monkeypatch.setattr(usedcar, "load_fetcher", lambda *_args: Fetcher())
    monkeypatch.setattr(usedcar, "sink_for", lambda *_args: sink)

    with pytest.raises(RuntimeError, match="used-car close failure"):
        usedcar.run_once(settings=settings, mode="initial", sink_name="sql")

    assert sink.closed is True
    assert json.loads(settings.state_path.read_text(encoding="utf-8"))["after_seq"] == 1
    events = _events(settings.log_path)
    assert events[-1]["event_name"] == "run_failed"
    assert events[-1]["error_code"] == "resource_close_failed"
    assert not any(event["event_name"] == "run_succeeded" for event in events)


def test_usedcar_mock_fetcher_close_failure_never_logs_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _settings(tmp_path)
    sink = _UsedCarSink(stats=LoadStats(inserted_count=1))

    class CloseFailingFetcher(_InitialWatermarkFetcher):
        def iter_initial(self, limit: int, max_batches: int) -> Any:
            yield _usedcar_page([{"id": 1}], sequence=1)

        def close(self) -> None:
            raise RuntimeError("mock used-car fetcher close failure")

    monkeypatch.setattr(usedcar, "load_fetcher", lambda *_args: CloseFailingFetcher())
    monkeypatch.setattr(usedcar, "sink_for", lambda *_args: sink)

    with pytest.raises(RuntimeError, match="fetcher close failure"):
        usedcar.run_once(settings=settings, mode="initial", sink_name="sql")

    assert sink.closed is True
    events = _events(settings.log_path)
    assert events[-1]["event_name"] == "run_failed"
    assert events[-1]["error_code"] == "resource_close_failed"
    assert not any(event["event_name"] == "run_succeeded" for event in events)


def test_faq_mock_primary_failure_survives_cleanup_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _settings(tmp_path)
    primary = FaqPreprocessError("primary FAQ failure", code="primary_faq")

    class FailingSink(_Sink):
        def close(self) -> None:
            self.closed = True
            raise RuntimeError("secondary FAQ close failure")

    sink = FailingSink(error=primary)
    monkeypatch.setattr(
        faq,
        "FaqCollector",
        lambda _settings: SimpleNamespace(
            iter_pages=lambda: iter([_faq_page([_faq_record()])])
        ),
    )
    monkeypatch.setattr(faq, "MongoFaqUpsertSink", lambda _settings: sink)

    with pytest.raises(FaqPreprocessError) as exc_info:
        faq.run_once(settings=settings, sink_name="mongo")

    assert exc_info.value is primary
    assert sink.closed is True
    events = _events(settings.log_path)
    assert [event["error_code"] for event in events[-2:]] == [
        "primary_faq",
        "resource_close_failed",
    ]
    assert not any(event["event_name"] == "run_succeeded" for event in events)


def test_usedcar_mock_primary_failure_survives_cleanup_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _settings(tmp_path)
    primary = PreprocessError("primary used-car failure", code="primary_usedcar")

    class FailingSink(_UsedCarSink):
        def close(self) -> None:
            self.closed = True
            raise RuntimeError("secondary used-car close failure")

    sink = FailingSink(error=primary)

    class Fetcher(_InitialWatermarkFetcher):
        def iter_initial(self, limit: int, max_batches: int) -> Any:
            yield _usedcar_page([{"id": 1}], sequence=1)

    monkeypatch.setattr(usedcar, "load_fetcher", lambda *_args: Fetcher())
    monkeypatch.setattr(usedcar, "sink_for", lambda *_args: sink)

    with pytest.raises(PreprocessError) as exc_info:
        usedcar.run_once(settings=settings, mode="initial", sink_name="sql")

    assert exc_info.value is primary
    assert sink.closed is True
    events = _events(settings.log_path)
    assert [event["error_code"] for event in events[-2:]] == [
        "primary_usedcar",
        "resource_close_failed",
    ]
    assert not settings.state_path.exists()


def test_registration_mock_primary_failure_survives_both_cleanup_failures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _settings(tmp_path)
    primary = RegistrationError(
        "primary registration failure",
        code="primary_registration",
    )
    payload = _registration_payload(
        {
            "date": "202608",
            "시도명": "서울",
            "시군구": "강남구",
            "승용>관용": 1,
        }
    )

    class Client:
        def __init__(self, _settings: Settings) -> None:
            pass

        def fetch_period(self, period: str, reserve_call: Any) -> tuple[Any, bytes]:
            reserve_call()
            return payload, b"primary-failure"

    class FailingSink(_Sink):
        def close(self) -> None:
            self.closed = True
            raise RuntimeError("secondary sink close failure")

    class FailingQuota(_Quota):
        def close(self) -> None:
            self.closed = True
            raise RuntimeError("secondary quota close failure")

    sink = FailingSink(error=primary)
    quota = FailingQuota()
    monkeypatch.setattr(registration, "RegistrationApiClient", Client)
    monkeypatch.setattr(registration, "SqlQuotaLedger", lambda _settings: quota)
    monkeypatch.setattr(
        registration,
        "SqlRegistrationUpsertSink",
        lambda _settings: sink,
    )

    with pytest.raises(RegistrationError) as exc_info:
        registration.run_once(
            settings=settings,
            sink_name="sql",
            period="2026-08",
        )

    assert exc_info.value is primary
    assert sink.closed is True
    assert quota.closed is True
    events = _events(settings.log_path)
    assert [event["error_code"] for event in events[-2:]] == [
        "primary_registration",
        "resource_close_failed",
    ]
    assert not any(event["event_name"] == "run_succeeded" for event in events)


def test_registration_mock_state_load_failure_closes_sql_quota(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _settings(tmp_path)
    quota = _Quota()

    class BrokenState:
        def __init__(self, _path: Path) -> None:
            pass

        def load(self) -> dict[str, Any]:
            raise registration.RegistrationError(
                "mock state failure", "state_unreadable"
            )

    monkeypatch.setattr(registration, "RegistrationStateStore", BrokenState)
    monkeypatch.setattr(registration, "SqlQuotaLedger", lambda _settings: quota)

    with pytest.raises(registration.RegistrationError) as exc_info:
        registration.run_once(
            settings=settings,
            sink_name="sql",
            period="2026-08",
        )

    assert exc_info.value.code == "state_unreadable"
    assert quota.closed is True


def test_registration_mock_load_failure_does_not_persist_success_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _settings(tmp_path)
    quota = _Quota()
    sink = _Sink(error=RuntimeError("mock registration SQL failure"))
    payload = _registration_payload(
        {"date": "202608", "시도명": "서울", "시군구": "강남구", "승용>관용": 1}
    )

    class Client:
        def __init__(self, _settings: Settings) -> None:
            pass

        def fetch_period(self, period: str, reserve_call: Any) -> tuple[Any, bytes]:
            reserve_call()
            return payload, b"mock-body"

    monkeypatch.setattr(registration, "RegistrationApiClient", Client)
    monkeypatch.setattr(registration, "SqlQuotaLedger", lambda _settings: quota)
    monkeypatch.setattr(
        registration, "SqlRegistrationUpsertSink", lambda _settings: sink
    )

    with pytest.raises(RuntimeError, match="mock registration SQL failure"):
        registration.run_once(settings=settings, sink_name="sql", period="2026-08")

    assert not settings.registration_state_path.exists()
    assert sink.closed is True
    assert quota.closed is True
    last_event = _events(settings.log_path)[-1]
    assert (last_event["event_name"], last_event["stage_name"]) == (
        "run_failed",
        "Load",
    )


def test_registration_mock_no_data_is_a_successful_zero_row_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _settings(tmp_path)
    sink = _Sink()

    class Client:
        def __init__(self, _settings: Settings) -> None:
            pass

        def fetch_period(self, period: str, reserve_call: Any) -> tuple[Any, bytes]:
            reserve_call()
            payload = {"status_code": "INFO-200", "result_data": {"formList": []}}
            return payload, b"no-data"

    monkeypatch.setattr(registration, "RegistrationApiClient", Client)
    monkeypatch.setattr(registration, "JsonlRegistrationUpsertSink", lambda _path: sink)

    result = registration.run_once(settings=settings, period="2026-08")

    assert result["periods"] == 1
    assert result["collected_count"] == 0
    assert result["inserted_count"] == 0
    assert sink.calls[0][0][0] == ()
    assert sink.closed is True


@pytest.mark.parametrize(
    ("settings_overrides", "kwargs", "message"),
    [
        ({}, {"sink_name": "mongo"}, "unsupported registration sink"),
        ({}, {"max_calls": 2}, "exactly one API call"),
        ({}, {"period": "2026-08", "start_period": "2026-09"}, "same month"),
        ({"registration_form_id": 1}, {}, "registration_form_id"),
        ({"registration_style_num": 1}, {}, "registration_style_num"),
    ],
)
def test_registration_mock_rejects_unsupported_operating_contracts(
    tmp_path: Path,
    settings_overrides: dict[str, Any],
    kwargs: dict[str, Any],
    message: str,
) -> None:
    settings = replace(_settings(tmp_path), **settings_overrides)

    with pytest.raises(ValueError, match=message):
        registration.run_once(settings=settings, **kwargs)

    assert not settings.log_path.exists()


def test_main_mock_all_dispatches_in_order_with_one_run_id_and_isolated_sinks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _settings(tmp_path / "configured")
    output_dir = tmp_path / "override"
    fixtures = {
        "faq": tmp_path / "faq.html",
        "registration": tmp_path / "registration.json",
        "usedcar": tmp_path / "usedcar.json",
    }
    for fixture in fixtures.values():
        fixture.write_text("{}", encoding="utf-8")

    calls: list[tuple[str, dict[str, Any]]] = []

    def worker(name: str) -> Any:
        def run_once(**kwargs: Any) -> dict[str, Any]:
            calls.append((name, kwargs))
            return {"status": "OK", "pipeline": name}

        return run_once

    monkeypatch.setattr(entrypoint, "settings_from_env", lambda: settings)
    monkeypatch.setattr(entrypoint.registration, "run_once", worker("registration"))
    monkeypatch.setattr(entrypoint.usedcar, "run_once", worker("usedcar"))
    monkeypatch.setattr(entrypoint.faq, "run_once", worker("faq"))
    args = entrypoint._parser().parse_args(
        [
            "--pipeline",
            "all",
            "--profile",
            "fixture",
            "--faq-fixture",
            str(fixtures["faq"]),
            "--registration-fixture",
            str(fixtures["registration"]),
            "--usedcar-fixture",
            str(fixtures["usedcar"]),
            "--faq-sink",
            "mongo",
            "--registration-sink",
            "sql",
            "--usedcar-sink",
            "sql",
            "--output-dir",
            str(output_dir),
        ]
    )

    result = entrypoint.run(args)

    assert [name for name, _kwargs in calls] == ["registration", "usedcar", "faq"]
    assert len({kwargs["run_id"] for _name, kwargs in calls}) == 1
    assert [kwargs["sink_name"] for _name, kwargs in calls] == ["sql", "sql", "mongo"]
    assert [kwargs["fixture"] for _name, kwargs in calls] == [
        fixtures["registration"],
        fixtures["usedcar"],
        fixtures["faq"],
    ]
    for _name, kwargs in calls:
        actual_settings = kwargs["settings"]
        assert actual_settings.output_dir == output_dir
        assert actual_settings.log_path == output_dir / "jsonl"
    assert result["status"] == "OK"
    assert list(result["results"]) == ["registration", "usedcar", "faq"]


def test_main_mock_all_stops_after_second_pipeline_failure_and_sanitizes_cli(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    settings = _settings(tmp_path)
    fixtures = {
        name: tmp_path / f"{name}.json" for name in ("registration", "usedcar", "faq")
    }
    for fixture in fixtures.values():
        fixture.write_text("{}", encoding="utf-8")
    calls: list[str] = []

    def complete_registration(**_kwargs: Any) -> dict[str, Any]:
        calls.append("registration")
        return {"status": "OK", "inserted_count": 1}

    def fail_usedcar(**_kwargs: Any) -> Any:
        calls.append("usedcar")
        raise FetchError("sensitive source detail", code="checkpoint_regression")

    def unexpected_faq(**_kwargs: Any) -> Any:
        calls.append("faq")
        pytest.fail("FAQ ran after the preceding pipeline failed")

    monkeypatch.setattr(entrypoint, "settings_from_env", lambda: settings)
    monkeypatch.setattr(entrypoint.registration, "run_once", complete_registration)
    monkeypatch.setattr(entrypoint.usedcar, "run_once", fail_usedcar)
    monkeypatch.setattr(entrypoint.faq, "run_once", unexpected_faq)

    assert (
        entrypoint.main(
            [
                "--pipeline",
                "all",
                "--profile",
                "fixture",
                "--registration-fixture",
                str(fixtures["registration"]),
                "--usedcar-fixture",
                str(fixtures["usedcar"]),
                "--faq-fixture",
                str(fixtures["faq"]),
            ]
        )
        == 1
    )

    assert calls == ["registration", "usedcar"]
    assert json.loads(capsys.readouterr().err) == {
        "status": "FAILED",
        "pipeline": "all",
        "error_code": "checkpoint_regression",
    }


def test_main_mock_all_preflights_every_fixture_before_first_worker(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    settings = _settings(tmp_path)
    registration_fixture = tmp_path / "registration.json"
    usedcar_fixture = tmp_path / "usedcar.json"
    registration_fixture.write_text("{}", encoding="utf-8")
    usedcar_fixture.write_text("{}", encoding="utf-8")
    calls: list[str] = []

    def unexpected(name: str) -> Any:
        def run_once(**_kwargs: Any) -> Any:
            calls.append(name)
            pytest.fail("pipeline ran before all fixtures passed preflight")

        return run_once

    monkeypatch.setattr(entrypoint, "settings_from_env", lambda: settings)
    monkeypatch.setattr(entrypoint.registration, "run_once", unexpected("registration"))
    monkeypatch.setattr(entrypoint.usedcar, "run_once", unexpected("usedcar"))
    monkeypatch.setattr(entrypoint.faq, "run_once", unexpected("faq"))

    assert (
        entrypoint.main(
            [
                "--pipeline",
                "all",
                "--profile",
                "fixture",
                "--registration-fixture",
                str(registration_fixture),
                "--usedcar-fixture",
                str(usedcar_fixture),
            ]
        )
        == 1
    )

    assert calls == []
    assert json.loads(capsys.readouterr().err) == {
        "status": "FAILED",
        "pipeline": "all",
        "error_code": "fixture_required",
    }


@pytest.mark.parametrize(
    ("settings_overrides", "sink_arguments"),
    [
        (
            {"sql_host": ""},
            ["--registration-sink", "json", "--usedcar-sink", "sql"],
        ),
        (
            {"sql_user": None},
            ["--registration-sink", "json", "--usedcar-sink", "sql"],
        ),
        (
            {"mongo_uri": ""},
            ["--registration-sink", "json", "--faq-sink", "mongo"],
        ),
    ],
)
def test_main_mock_all_preflights_sink_configuration_before_first_worker(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    settings_overrides: dict[str, Any],
    sink_arguments: list[str],
) -> None:
    settings = replace(_settings(tmp_path), **settings_overrides)
    fixtures = {
        name: tmp_path / f"{name}.json" for name in ("registration", "usedcar", "faq")
    }
    for fixture in fixtures.values():
        fixture.write_text("{}", encoding="utf-8")
    calls: list[str] = []

    def unexpected(name: str) -> Any:
        def run_once(**_kwargs: Any) -> Any:
            calls.append(name)
            pytest.fail("pipeline ran before sink configuration passed preflight")

        return run_once

    monkeypatch.setattr(entrypoint, "settings_from_env", lambda: settings)
    monkeypatch.setattr(entrypoint.registration, "run_once", unexpected("registration"))
    monkeypatch.setattr(entrypoint.usedcar, "run_once", unexpected("usedcar"))
    monkeypatch.setattr(entrypoint.faq, "run_once", unexpected("faq"))

    argv = [
        "--pipeline",
        "all",
        "--profile",
        "fixture",
        "--registration-fixture",
        str(fixtures["registration"]),
        "--usedcar-fixture",
        str(fixtures["usedcar"]),
        "--faq-fixture",
        str(fixtures["faq"]),
        *sink_arguments,
    ]

    assert entrypoint.main(argv) == 1
    assert calls == []
    assert json.loads(capsys.readouterr().err) == {
        "status": "FAILED",
        "pipeline": "all",
        "error_code": "sink_configuration",
    }


def test_main_mock_dry_run_does_not_require_persistent_sink_configuration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = replace(
        _settings(tmp_path),
        sql_host="",
        sql_user=None,
        mongo_uri="",
    )
    fixtures = {
        name: tmp_path / f"{name}.json" for name in ("registration", "usedcar", "faq")
    }
    for fixture in fixtures.values():
        fixture.write_text("{}", encoding="utf-8")
    calls: list[tuple[str, dict[str, Any]]] = []

    def worker(name: str) -> Any:
        def run_once(**kwargs: Any) -> dict[str, Any]:
            calls.append((name, kwargs))
            return {"status": "OK", "pipeline": name}

        return run_once

    monkeypatch.setattr(entrypoint, "settings_from_env", lambda: settings)
    monkeypatch.setattr(entrypoint.registration, "run_once", worker("registration"))
    monkeypatch.setattr(entrypoint.usedcar, "run_once", worker("usedcar"))
    monkeypatch.setattr(entrypoint.faq, "run_once", worker("faq"))
    args = entrypoint._parser().parse_args(
        [
            "--pipeline",
            "all",
            "--profile",
            "fixture",
            "--registration-fixture",
            str(fixtures["registration"]),
            "--usedcar-fixture",
            str(fixtures["usedcar"]),
            "--faq-fixture",
            str(fixtures["faq"]),
            "--registration-sink",
            "sql",
            "--usedcar-sink",
            "sql",
            "--faq-sink",
            "mongo",
            "--dry-run",
        ]
    )

    result = entrypoint.run(args)

    assert [name for name, _kwargs in calls] == ["registration", "usedcar", "faq"]
    assert all(kwargs["dry_run"] is True for _name, kwargs in calls)
    assert result["status"] == "OK"


@pytest.mark.parametrize("module", [registration, usedcar])
def test_pipeline_mock_driver_error_is_logged_and_cli_is_sanitized(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    module: Any,
) -> None:
    class DriverOperationalError(Exception):
        pass

    settings = _settings(tmp_path / module.__name__.split(".")[-1])

    if module is registration:
        quota = _Quota()
        payload = _registration_payload(
            {
                "date": "202608",
                "시도명": "서울",
                "시군구": "강남구",
                "승용>관용": 1,
            }
        )

        class Client:
            def __init__(self, _settings: Settings) -> None:
                pass

            def fetch_period(self, period: str, reserve_call: Any) -> tuple[Any, bytes]:
                reserve_call()
                return payload, b"driver-error"

        sink = _Sink(error=DriverOperationalError("secret DB endpoint"))
        monkeypatch.setattr(registration, "RegistrationApiClient", Client)
        monkeypatch.setattr(registration, "SqlQuotaLedger", lambda _settings: quota)
        monkeypatch.setattr(
            registration,
            "SqlRegistrationUpsertSink",
            lambda _settings: sink,
        )
        with pytest.raises(DriverOperationalError):
            registration.run_once(
                settings=settings,
                sink_name="sql",
                period="2026-08",
            )
    else:
        sink = _UsedCarSink(error=DriverOperationalError("secret DB endpoint"))

        class Fetcher(_InitialWatermarkFetcher):
            def iter_initial(self, limit: int, max_batches: int) -> Any:
                yield _usedcar_page([{"id": 1}], sequence=1)

        monkeypatch.setattr(usedcar, "load_fetcher", lambda *_args: Fetcher())
        monkeypatch.setattr(usedcar, "sink_for", lambda *_args: sink)
        with pytest.raises(DriverOperationalError):
            usedcar.run_once(settings=settings, mode="initial", sink_name="sql")

    last_event = _events(settings.log_path)[-1]
    assert last_event["event_name"] == "run_failed"
    assert last_event["error_code"] in {"registration_error", "run_failed"}
    capsys.readouterr()

    monkeypatch.setattr(module, "settings_from_env", lambda: settings)

    def fail_cli(**_kwargs: Any) -> Any:
        raise DriverOperationalError("secret DB endpoint")

    monkeypatch.setattr(module, "run_once", fail_cli)
    assert module.main([]) == 1
    error = json.loads(capsys.readouterr().err)
    assert error["status"] == "FAILED"
    assert error["error_code"] in {"registration_error", "run_failed"}
    assert "secret" not in json.dumps(error)


@pytest.mark.parametrize(
    ("argv", "error_code"),
    [
        (
            ["--pipeline", "faq", "--profile", "live", "--fixture", "unused.html"],
            "fixture_profile_conflict",
        ),
        (
            ["--pipeline", "all", "--profile", "fixture", "--sink", "json"],
            "sink_argument",
        ),
        (
            ["--pipeline", "faq", "--profile", "fixture"],
            "fixture_required",
        ),
    ],
)
def test_main_mock_reports_sanitized_operating_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    argv: list[str],
    error_code: str,
) -> None:
    monkeypatch.setattr(entrypoint, "settings_from_env", lambda: _settings(tmp_path))

    assert entrypoint.main(argv) == 1

    error = json.loads(capsys.readouterr().err)
    assert error == {"status": "FAILED", "pipeline": argv[1], "error_code": error_code}


def test_individual_pipeline_mock_clis_report_success_and_sanitized_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    base_settings = _settings(tmp_path / "base")

    for module in (faq, usedcar, registration):
        monkeypatch.setattr(module, "settings_from_env", lambda: base_settings)
        monkeypatch.setattr(
            module,
            "run_once",
            lambda **_kwargs: {"status": "OK", "run_id": "mock-cli"},
        )
        output_dir = tmp_path / module.__name__.split(".")[-1]
        assert module.main(["--output-dir", str(output_dir)]) == 0
        assert json.loads(capsys.readouterr().out)["status"] == "OK"

    def fail(**_kwargs: Any) -> Any:
        raise RegistrationError("secret upstream detail", code="safe_error")

    monkeypatch.setattr(registration, "run_once", fail)
    assert registration.main([]) == 1
    assert json.loads(capsys.readouterr().err) == {
        "status": "FAILED",
        "error_code": "safe_error",
    }
