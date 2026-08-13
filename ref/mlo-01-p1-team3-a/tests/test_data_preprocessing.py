from __future__ import annotations

import json
from pathlib import Path

from collection.faq import parse_faq_html
from collection.registration import extract_record_list
from collection.usedcar import UsedCarFetcher
from common.config import Settings
from common.logging_utils import redact
from loading.faq import JsonlFaqUpsertSink
from loading.registration import JsonlRegistrationUpsertSink
from loading.usedcar import JsonlUpsertSink
from pipelines.faq import run_once as run_faq_once
from pipelines.registration import run_once as run_registration_once
from pipelines.usedcar import run_once
from preprocessing.faq import transform_faq_records
from preprocessing.registration import transform_registration_records
from preprocessing.usedcar import transform_record
from migrations.sql.run import split_sql


ROOT = Path(__file__).resolve().parents[1]
INITIAL_FIXTURE = ROOT / "tests" / "fixtures" / "usedcar_initial.json"
CHANGES_FIXTURE = ROOT / "tests" / "fixtures" / "usedcar_changes.json"
FAQ_FIXTURE = ROOT / "tests" / "fixtures" / "faq.html"
REGISTRATION_FIXTURE = ROOT / "tests" / "fixtures" / "registration.json"


def make_settings(tmp_path: Path) -> Settings:
    return Settings(
        base_url="http://192.168.0.51:4000",
        api_key=None,
        output_dir=tmp_path,
        state_path=tmp_path / "usedcar_checkpoint.json",
        log_path=tmp_path / "jsonl",
        batch_size=500,
        initial_target=10000,
        max_batches=20,
        interval_seconds=1.0,
        timeout_seconds=5.0,
        user_agent="test",
        sql_host="",
        sql_port=3306,
        sql_database="sales_support_db",
        sql_user="",
        sql_password="",
        faq_source_url="http://192.168.0.51:4000/faqs",
        registration_state_path=tmp_path / "registration_state.json",
    )


def test_legacy_molit_environment_names_do_not_change_used_car_source() -> None:
    settings = Settings.from_env(
        env={
            "BASE_URL": "https://stat.molit.go.kr/legacy",
            "API_KEY_1": "legacy-value",
        }
    )

    assert settings.base_url == "http://192.168.0.51:4000"
    assert settings.api_key is None


def test_database_connection_settings_are_env_driven_and_empty_password_is_none() -> None:
    settings = Settings.from_env(
        env={
            "SQL_JDBC_URL": "jdbc:mysql://localhost:3306/sales_support_db",
            "SQL_USER": "root",
            "SQL_PASSWORD": "",
            "MONGODB_HOST": "localhost",
            "MONGODB_PORT": "27017",
            "MONGODB_USER": "",
            "MONGODB_PASSWORD": "",
        }
    )

    assert settings.sql_host == "localhost"
    assert settings.sql_port == 3306
    assert settings.sql_database == "sales_support_db"
    assert settings.sql_user == "root"
    assert settings.sql_password is None
    assert settings.mongo_uri == "mongodb://localhost:27017/"
    assert settings.mongo_user is None
    assert settings.mongo_password is None


def test_transform_uses_documented_camel_case_fields() -> None:
    row = transform_record(
        {
            "id": 1,
            "listingNumber": "UC-1",
            "title": "2024 현대 그랜저",
            "description": "fixture description",
            "brand": {"id": 1, "name": "현대", "slug": "hyundai"},
            "model": {"id": 11, "name": "그랜저", "slug": "grandeur", "bodyType": "sedan"},
            "modelYear": 2024,
            "firstRegistration": "2024-04-22",
            "mileageKm": 100,
            "price": 10000000,
            "currency": "KRW",
            "status": "AVAILABLE",
            "location": {"id": 1, "province": "서울특별시", "city": "서울", "slug": "seoul"},
            "dealer": {"code": "D-001", "displayName": "교○○"},
            "businessArea": {
                "id": "BIZ_001",
                "name": "소매",
                "parent": {"id": "BIZ_000", "name": "영업"},
            },
            "fuelType": "가솔린",
            "transmission": "자동",
            "color": "검정색",
            "displacementCc": 1998,
            "accidentCount": 0,
            "ownerChangeCount": 1,
            "inspectionStatus": "점검완료",
            "createdAt": "2026-08-11T00:00:00+09:00",
            "updatedAt": "2026-08-11T01:00:00+09:00",
        },
        base_url="http://192.168.0.51:4000",
        run_id="run-1",
        collected_at="2026-08-11T00:00:00+00:00",
        dataset_epoch="epoch-1",
    )

    assert row["listing"]["listing_id"] == "1"
    assert row["brand"]["name"] == "현대"
    assert row["model"]["name"] == "그랜저"
    assert row["model"]["body_type"] == "sedan"
    assert row["listing"]["model_id"] == 11
    assert "brand_id" not in row["listing"]
    assert "normalized_status" not in row["listing"]
    assert row["business_area"]["parent"]["business_area_id"] == "BIZ_000"
    assert "parent_name" not in row["business_area"]
    assert row["listing"]["price_krw"] == 10000000
    assert row["listing"]["source_status"] == "AVAILABLE"
    assert row["listing"]["fuel_type"] == "가솔린"
    assert len(row["listing"]["content_hash"]) == 64


def test_initial_fixture_is_one_bounded_run_and_is_idempotent(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    first = run_once(settings=settings, mode="initial", fixture=INITIAL_FIXTURE)
    second = run_once(settings=settings, mode="initial", fixture=INITIAL_FIXTURE)

    assert first["status"] == "OK"
    assert first["batches"] == 2
    assert first["collected_count"] == 3
    assert second["inserted_count"] == 0
    assert second["unchanged_count"] == 3
    checkpoint = json.loads((tmp_path / "usedcar_checkpoint.json").read_text())
    assert checkpoint["initialized"] is True
    assert checkpoint["dataset_epoch"] == "epoch-2026-08-11"


def test_incremental_fixture_updates_existing_listing_once(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    run_once(settings=settings, mode="initial", fixture=INITIAL_FIXTURE)
    result = run_once(settings=settings, mode="incremental", fixture=CHANGES_FIXTURE)

    assert result["status"] == "OK"
    assert result["updated_count"] == 1
    checkpoint = json.loads((tmp_path / "usedcar_checkpoint.json").read_text())
    assert checkpoint["after_seq"] == 3

    rows = [
        json.loads(line)
        for line in (tmp_path / "vehicle_listings.jsonl").read_text().splitlines()
        if line.strip()
    ]
    updated = next(row for row in rows if row["listing"]["listing_id"] == "100053")
    assert updated["listing"]["mileage_km"] == 12500
    assert updated["listing"]["price_krw"] == 31500000


def test_jsonl_sink_does_not_duplicate_a_listing(tmp_path: Path) -> None:
    sink = JsonlUpsertSink(tmp_path / "vehicle_listings.jsonl")
    row = {"listing": {"listing_id": "1", "content_hash": "same"}, "value": 1}
    assert sink.save([row]).inserted_count == 1
    assert sink.save([row]).unchanged_count == 1
    assert len((tmp_path / "vehicle_listings.jsonl").read_text().splitlines()) == 1


def test_live_fetcher_enforces_one_second_between_batch_starts() -> None:
    class Clock:
        def __init__(self) -> None:
            self.now = 0.0
            self.sleeps = []

        def monotonic(self) -> float:
            return self.now

        def sleep(self, seconds: float) -> None:
            self.sleeps.append(seconds)
            self.now += seconds

    class Client:
        def __init__(self) -> None:
            self.calls = []
            self.pages = [
                {
                    "data": [{"id": 2}],
                    "meta": {"has_more": True},
                    "links": {"next": "/api/v1/cars/cursor?after_id=2&limit=500"},
                },
                {
                    "data": [{"id": 1}],
                    "meta": {"has_more": False},
                    "links": {},
                },
            ]

        def get(self, path: str, **kwargs):
            self.calls.append((path, kwargs))
            return self.pages.pop(0)

    clock = Clock()
    client = Client()
    fetcher = UsedCarFetcher(
        client, interval_seconds=1.0, monotonic=clock.monotonic, sleeper=clock.sleep
    )
    pages = list(fetcher.iter_initial(limit=500, max_batches=2))

    assert len(pages) == 2
    assert len(client.calls) == 2
    assert clock.sleeps == [1.0]


def test_faq_fixture_is_parsed_and_mongo_contract_is_idempotent(tmp_path: Path) -> None:
    page = parse_faq_html(FAQ_FIXTURE.read_bytes(), "fixture://faqs")
    assert len(page.records) == 2
    assert page.records[0]["faq_id"] == "hyundai-support-001"
    assert page.records[0]["brand"] == "hyundai"
    assert page.records[0]["category"] == "고객지원"
    assert page.records[0]["source_url"].endswith("/customer/center/faq")
    assert page.records[0]["question"].startswith("공식 FAQ")
    fallback_record = dict(page.records[0])
    fallback_record.pop("faq_id")
    fallback_rows, fallback_rejected = transform_faq_records(
        [fallback_record],
        settings=make_settings(tmp_path),
        run_id="run-faq",
        collected_at="2026-08-11T00:00:00+00:00",
    )
    assert not fallback_rejected
    assert len(fallback_rows[0]["faq_id"]) == 64

    settings = make_settings(tmp_path)
    first = run_faq_once(settings=settings, fixture=FAQ_FIXTURE)
    second = run_faq_once(settings=settings, fixture=FAQ_FIXTURE)

    assert first["inserted_count"] == 2
    assert second["unchanged_count"] == 2
    assert len((tmp_path / "faq.jsonl").read_text(encoding="utf-8").splitlines()) == 2


def test_faq_parser_uses_beautifulsoup_for_nested_text_and_pagination() -> None:
    body = """
    <main>
      <article class="faq-item" data-faq-id="nested-001" data-brand="test" data-category="학습"
          data-reviewed-at="2026-08-12" data-source-url="https://example.com/source">
        <h2 data-field="question">질문 <em>내용</em></h2>
        <p data-field="answer">답변<br><strong>강조</strong></p>
        <time data-field="reviewed-at" datetime="2026-08-12">확인일</time>
        <a data-field="source" href="https://example.com/faq">출처</a>
      </article>
      <a rel="next" href="/faqs?page=2">다음</a>
    </main>
    """

    page = parse_faq_html(body, "http://192.168.0.51:4000/faqs")

    assert page.records == [
        {
            "faq_id": "nested-001",
            "brand": "test",
            "category": "학습",
            "reviewed_at": "2026-08-12",
            "source_url": "https://example.com/faq",
            "question": "질문 내용",
            "answer": "답변 강조",
        }
    ]
    assert page.next_url == "http://192.168.0.51:4000/faqs?page=2"


def test_registration_transform_flattens_all_api_measures_and_preserves_business_key(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    payload = json.loads(REGISTRATION_FIXTURE.read_text(encoding="utf-8"))
    raw = extract_record_list(payload["pages"][0]["payload"])[0]
    rows, rejected = transform_registration_records(
        [raw],
        period="202606",
        settings=settings,
        run_id="run-registration",
        collected_at="2026-08-11T00:00:00+00:00",
    )

    assert rejected == []
    assert len(rows) == 20
    assert {
        (row["report_month"], row["sido_name"], row["sigungu_name"], row["vehicle_type"], row["usage_type"])
        for row in rows
    } >= {
        ("2026-06-01", "서울", "강남구", "승용", "관용"),
        ("2026-06-01", "서울", "강남구", "총계", "계"),
    }
    assert next(
        row for row in rows if row["vehicle_type"] == "승용" and row["usage_type"] == "관용"
    )["quantity"] == 156


def test_registration_fixture_runs_once_per_day_and_flattens_rows(tmp_path: Path) -> None:
    settings = Settings(
        **{
            **make_settings(tmp_path).__dict__,
            "registration_daily_quota": 3,
            "registration_state_path": tmp_path / "registration_state.json",
        }
    )
    result = run_registration_once(
        settings=settings,
        fixture=REGISTRATION_FIXTURE,
        period="2026-06",
    )

    assert result["status"] == "OK"
    assert result["period"] == "2026-06"
    assert result["api_calls"] == 1
    assert result["collected_count"] == 2
    assert result["preprocessed_count"] == 40
    assert result["valid_count"] == 40
    assert result["quota_used"] == 1

    second = run_registration_once(
        settings=settings,
        fixture=REGISTRATION_FIXTURE,
        period="2026-06",
    )
    assert second["api_calls"] == 1
    assert second["unchanged_count"] == 40
    assert len((tmp_path / "vehicle_registration_reports.jsonl").read_text(encoding="utf-8").splitlines()) == 40


def test_registration_jsonl_sink_upserts_business_key_without_duplicates(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    rows, rejected = transform_registration_records(
        [{"date": "202606", "시도명": "서울", "시군구": "강남구", "승용>관용": 10}],
        period="202606",
        settings=settings,
        run_id="run-registration",
        collected_at="2026-08-11T00:00:00+00:00",
    )
    assert not rejected
    sink = JsonlRegistrationUpsertSink(tmp_path / "registration.jsonl")
    assert sink.save(rows).inserted_count == 1
    assert sink.save(rows).unchanged_count == 1
    assert len((tmp_path / "registration.jsonl").read_text(encoding="utf-8").splitlines()) == 1


def test_sql_and_mongo_migrations_match_business_key_contract() -> None:
    sql = (ROOT / "migrations" / "sql" / "V001__mvp_schema.sql").read_text(encoding="utf-8")
    mongo = (ROOT / "migrations" / "mongo" / "ensure_indexes.py").read_text(encoding="utf-8")
    listings_sql = sql.split("CREATE TABLE IF NOT EXISTS vehicle_listings", 1)[1].split(") ENGINE=InnoDB", 1)[0]
    business_areas_sql = sql.split("CREATE TABLE IF NOT EXISTS vehicle_business_areas", 1)[1].split(") ENGINE=InnoDB", 1)[0]

    assert "CREATE TABLE IF NOT EXISTS vehicle_listings" in sql
    assert "CREATE TABLE IF NOT EXISTS vehicle_brands" in sql
    assert "CREATE TABLE IF NOT EXISTS vehicle_models" in sql
    assert "CREATE TABLE IF NOT EXISTS vehicle_locations" in sql
    assert "CREATE TABLE IF NOT EXISTS vehicle_dealers" in sql
    assert "CREATE TABLE IF NOT EXISTS vehicle_business_areas" in sql
    assert "CONSTRAINT fk_listing_model" in sql
    assert "vehicle_listing_detail" not in sql
    assert "brand_id" not in listings_sql
    assert "normalized_status" not in listings_sql
    assert "parent_name" not in business_areas_sql
    assert "location_json" not in sql
    assert "CREATE TABLE IF NOT EXISTS vehicle_registration_reports" in sql
    assert "content_hash CHAR(64) NULL" in sql
    assert "report_month DATE NOT NULL" in sql
    assert "sido_name VARCHAR(128) NOT NULL" in sql
    assert "sigungu_name VARCHAR(128) NOT NULL" in sql
    assert "usage_type VARCHAR(128) NOT NULL" in sql
    assert "quantity BIGINT NULL" in sql
    assert "(report_month, sido_name, sigungu_name, vehicle_type, usage_type)" in sql
    assert "CREATE TABLE IF NOT EXISTS pipeline_runs" in sql
    assert "CREATE TABLE IF NOT EXISTS api_quota_usage" in sql
    assert "CREATE TABLE IF NOT EXISTS application_logs" in sql
    assert 'name="uq_faq_id"' in mongo
    assert 'name="ix_faq_brand_category"' in mongo
    assert 'name="ix_faq_updated_at"' in mongo
    assert 'validationAction="error"' in mongo
    assert len(split_sql(sql)) >= 10
    assert not (ROOT / "migrations" / "sql" / "V002__normalize_registration_reports.sql").exists()


def test_configuration_enforces_mvp_limits_and_redacts_secrets() -> None:
    settings = Settings.from_env(
        env={
            "FAQ_SOURCE_URL": "http://192.168.0.51:4000/faqs",
            "FAQ_ALLOWED_PATHS": "/faqs",
            "REGISTRATION_DAILY_QUOTA": "3000",
            "REGISTRATION_API_KEY": "do-not-log",
        }
    )
    assert settings.faq_source_url.endswith("/faqs")
    assert settings.registration_daily_quota == 3000
    assert redact({"api_key": "do-not-log", "mongodb_uri": "mongodb://user:pass@host/db"}) == {
        "api_key": "[REDACTED]",
        "mongodb_uri": "[REDACTED]",
    }

    try:
        Settings.from_env(env={"REGISTRATION_DAILY_QUOTA": "3001"})
    except ValueError as exc:
        assert "REGISTRATION_DAILY_QUOTA" in str(exc)
    else:
        raise AssertionError("quota above 3,000 must be rejected")
