from __future__ import annotations

import os
import re
import uuid
from dataclasses import replace
from typing import Any, Iterator

import pytest

from common.config import Settings


LIVE_ENABLE = "MLO_LIVE_TESTS"
LIVE_WRITE_ENABLE = "MLO_LIVE_WRITE"
_TEST_DATABASE_PATTERN = re.compile(r"mlo_live_test_[0-9a-f]{12}\Z")


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "live: requires configured external services")
    config.addinivalue_line(
        "markers",
        "live_write: writes only to isolated mlo_live_test_* databases",
    )


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    live_enabled = os.environ.get(LIVE_ENABLE) == "1"
    write_enabled = os.environ.get(LIVE_WRITE_ENABLE) == "1"
    for item in items:
        if "live" in item.keywords and not live_enabled:
            item.add_marker(
                pytest.mark.skip(reason=f"set {LIVE_ENABLE}=1 to run live tests")
            )
        if "live_write" in item.keywords and not write_enabled:
            item.add_marker(
                pytest.mark.skip(
                    reason=f"set {LIVE_WRITE_ENABLE}=1 to allow isolated writes"
                )
            )


@pytest.fixture(scope="session")
def live_settings(tmp_path_factory: pytest.TempPathFactory) -> Settings:
    settings = Settings.from_env()
    output_dir = tmp_path_factory.mktemp("live-output")
    return replace(
        settings,
        output_dir=output_dir,
        state_path=output_dir / "usedcar_checkpoint.json",
        registration_state_path=output_dir / "registration_state.json",
        faq_state_path=output_dir / "faq_checkpoint.json",
        log_path=output_dir / "live-events.jsonl",
        batch_size=25,
        initial_target=50,
        max_batches=2,
        interval_seconds=1.0,
        faq_interval_seconds=1.0,
    )


def _connect_mysql(settings: Settings, *, database: str | None = None) -> Any:
    import pymysql

    kwargs: dict[str, Any] = {
        "host": settings.sql_host,
        "port": settings.sql_port,
        "user": settings.sql_user,
        "password": settings.sql_password,
        "charset": "utf8mb4",
        "autocommit": False,
    }
    if database is not None:
        kwargs["database"] = database
    return pymysql.connect(**kwargs)


@pytest.fixture
def isolated_sql_settings(live_settings: Settings) -> Iterator[Settings]:
    if not live_settings.sql_host or not live_settings.sql_user:
        pytest.fail("enabled SQL live tests require SQL_HOST and SQL_USER")
    database = f"mlo_live_test_{uuid.uuid4().hex[:12]}"
    assert _TEST_DATABASE_PATTERN.fullmatch(database)
    admin = _connect_mysql(live_settings)
    tables = (
        "vehicle_brands",
        "vehicle_models",
        "vehicle_locations",
        "vehicle_dealers",
        "vehicle_business_areas",
        "vehicle_listings",
        "vehicle_registration_reports",
        "pipeline_runs",
        "api_quota_usage",
    )
    quoted_database = f"`{database}`"
    source_database = live_settings.sql_database
    if not re.fullmatch(r"[A-Za-z0-9_]+", source_database):
        raise AssertionError("configured SQL_DATABASE is not a safe identifier")
    owned = False
    try:
        with admin.cursor() as cursor:
            cursor.execute(
                "SELECT COUNT(*) FROM information_schema.SCHEMATA WHERE SCHEMA_NAME=%s",
                (database,),
            )
            if cursor.fetchone()[0] != 0:
                pytest.fail("generated SQL live-test database already exists")
            cursor.execute(
                f"CREATE DATABASE {quoted_database} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
            owned = True
            for table in tables:
                cursor.execute(
                    f"CREATE TABLE {quoted_database}.`{table}` "
                    f"LIKE `{source_database}`.`{table}`"
                )
            cursor.execute(
                f"ALTER TABLE {quoted_database}.vehicle_models "
                f"ADD CONSTRAINT fk_model_brand FOREIGN KEY (brand_id) "
                f"REFERENCES {quoted_database}.vehicle_brands (brand_id)"
            )
            cursor.execute(
                f"ALTER TABLE {quoted_database}.vehicle_business_areas "
                f"ADD CONSTRAINT fk_business_area_parent "
                f"FOREIGN KEY (parent_business_area_id) "
                f"REFERENCES {quoted_database}.vehicle_business_areas (business_area_id)"
            )
            for name, column, table, key in (
                ("fk_listing_model", "model_id", "vehicle_models", "model_id"),
                (
                    "fk_listing_location",
                    "location_id",
                    "vehicle_locations",
                    "location_id",
                ),
                (
                    "fk_listing_dealer",
                    "dealer_code",
                    "vehicle_dealers",
                    "dealer_code",
                ),
                (
                    "fk_listing_business_area",
                    "business_area_id",
                    "vehicle_business_areas",
                    "business_area_id",
                ),
            ):
                cursor.execute(
                    f"ALTER TABLE {quoted_database}.vehicle_listings "
                    f"ADD CONSTRAINT {name} FOREIGN KEY ({column}) "
                    f"REFERENCES {quoted_database}.{table} ({key})"
                )
        admin.commit()
        yield replace(live_settings, sql_database=database)
    finally:
        try:
            admin.rollback()
            if owned:
                with admin.cursor() as cursor:
                    cursor.execute(f"DROP DATABASE {quoted_database}")
                admin.commit()
        finally:
            admin.close()


@pytest.fixture
def isolated_mongo_settings(live_settings: Settings) -> Iterator[Settings]:
    if not live_settings.mongo_uri:
        pytest.fail("enabled Mongo live tests require MONGODB_URI")
    database = f"mlo_live_test_{uuid.uuid4().hex[:12]}"
    assert _TEST_DATABASE_PATTERN.fullmatch(database)
    collection = "faq"
    settings = replace(
        live_settings,
        mongo_database=database,
        mongo_collection=collection,
    )
    owned = False
    client = None
    try:
        from pymongo import MongoClient

        client = MongoClient(
            live_settings.mongo_uri,
            serverSelectionTimeoutMS=live_settings.mongo_server_selection_timeout_ms,
            tz_aware=True,
        )
        if database in client.list_database_names():
            pytest.fail("generated Mongo live-test database already exists")
        from migrations.mongo.ensure_indexes import ensure_indexes

        owned = True
        ensure_indexes(
            uri=live_settings.mongo_uri,
            database=database,
            collection=collection,
            server_selection_timeout_ms=live_settings.mongo_server_selection_timeout_ms,
        )
        yield settings
    finally:
        if client is not None:
            try:
                if owned:
                    client.drop_database(database)
            finally:
                client.close()


@pytest.fixture
def registration_sql_settings(isolated_sql_settings: Settings) -> Settings:
    if not isolated_sql_settings.registration_api_key:
        pytest.fail("enabled registration live tests require REGISTRATION_API_KEY")
    return isolated_sql_settings


@pytest.fixture
def sql_connection(isolated_sql_settings: Settings) -> Iterator[Any]:
    connection = _connect_mysql(
        isolated_sql_settings, database=isolated_sql_settings.sql_database
    )
    try:
        yield connection
    finally:
        connection.close()
