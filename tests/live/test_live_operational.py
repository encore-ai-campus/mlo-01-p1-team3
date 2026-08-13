from __future__ import annotations

import copy
import json
from dataclasses import replace
from datetime import datetime, timezone
from typing import Any, Mapping

import pytest

from collection.api import ApiClient
from collection.faq import FaqCollector
from collection.registration import RegistrationApiClient, extract_record_list
from collection.usedcar import UsedCarFetcher, page_checkpoint
from common.config import Settings
from common.contracts import LoadStats
from common.usedcar_hash import usedcar_content_hash
from loading.faq import MongoFaqUpsertSink
from loading.registration import SqlRegistrationUpsertSink
from loading.usedcar import SqlUpsertSink
from pipelines import faq, registration, usedcar
from preprocessing.faq import transform_faq_record, transform_faq_records
from preprocessing.registration import transform_registration_records
from preprocessing.usedcar import transform_record, transform_records


pytestmark = [pytest.mark.live, pytest.mark.live_write]


def _fetch_faq(settings: Settings) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    raw = [
        record
        for page in FaqCollector(settings).iter_pages()
        for record in page.records
    ]
    prepared, rejected = transform_faq_records(
        raw,
        settings=settings,
        run_id="live-faq-evidence",
        collected_at=datetime.now(timezone.utc).isoformat(),
    )
    assert rejected == []
    return raw, prepared


def _mysql_rows(connection: Any, query: str, params: tuple[Any, ...] = ()) -> list[Any]:
    with connection.cursor() as cursor:
        cursor.execute(query, params)
        return list(cursor.fetchall())


def _registration_raw(settings: Settings, period: str) -> list[Mapping[str, Any]]:
    calls = 0

    def reserve() -> None:
        nonlocal calls
        calls += 1

    payload, _body = RegistrationApiClient(settings).fetch_period(period, reserve)
    assert calls >= 1
    return list(extract_record_list(payload))


def _detail_measure_count(records: list[Mapping[str, Any]]) -> int:
    count = 0
    for record in records:
        for raw_key in record:
            key = str(raw_key).strip()
            if ">" not in key:
                continue
            vehicle_type, usage_type = (part.strip() for part in key.split(">", 1))
            if (
                vehicle_type
                and usage_type
                and vehicle_type != "총계"
                and usage_type != "계"
            ):
                count += 1
    return count


def test_live_faq_full_source_upsert_and_readback_integrity(
    isolated_mongo_settings: Settings,
) -> None:
    from pymongo import MongoClient

    settings = isolated_mongo_settings
    raw, prepared = _fetch_faq(settings)
    assert raw
    assert len({row["faq_id"] for row in prepared}) == len(prepared)

    first = faq.run_once(settings=settings, sink_name="mongo")
    second = faq.run_once(settings=settings, sink_name="mongo")

    assert first["collected_count"] == len(raw)
    assert first["inserted_count"] == len(prepared)
    assert first["updated_count"] == first["unchanged_count"] == 0
    assert second["collected_count"] == len(raw)
    assert second["unchanged_count"] == len(prepared)
    assert second["inserted_count"] == second["updated_count"] == 0

    client = MongoClient(settings.mongo_uri, tz_aware=True)
    try:
        collection = client[settings.mongo_database][settings.mongo_collection]
        stored = list(collection.find({}, {"_id": 0}))
        assert collection.count_documents({}) == len(prepared)
        assert len(collection.distinct("faq_id")) == len(prepared)
        expected = {row["faq_id"]: row["content_hash"] for row in prepared}
        assert {row["faq_id"]: row["content_hash"] for row in stored} == expected
        assert all(
            isinstance(row[field], datetime)
            for row in stored
            for field in (
                "source_updated_at",
                "collected_at",
                "created_at",
                "updated_at",
            )
        )
        index = collection.index_information()["uq_faq_id"]
        assert index["unique"] is True
        assert index["key"] == [("faq_id", 1)]
    finally:
        client.close()


def test_live_faq_changed_content_updates_without_duplicate(
    isolated_mongo_settings: Settings,
) -> None:
    settings = isolated_mongo_settings
    raw, prepared = _fetch_faq(settings)
    original = prepared[0]
    changed_raw = dict(raw[0])
    changed_raw["answer"] = f"{changed_raw['answer']} [live update probe]"
    changed = transform_faq_record(
        changed_raw,
        settings=settings,
        run_id="live-faq-update",
        collected_at=datetime.now(timezone.utc).isoformat(),
    )
    sink = MongoFaqUpsertSink(settings)
    try:
        inserted = sink.save([original])
        unchanged = sink.save([original])
        updated = sink.save([changed])
        restored = sink.save([original])
        assert (inserted.inserted_count, unchanged.unchanged_count) == (1, 1)
        assert (updated.updated_count, restored.updated_count) == (1, 1)
        stored = sink._collection.find_one({"faq_id": original["faq_id"]})
        assert stored is not None
        assert stored["content_hash"] == original["content_hash"]
        assert sink._collection.count_documents({"faq_id": original["faq_id"]}) == 1
    finally:
        sink.close()


def test_live_usedcar_initial_insert_unchanged_update_and_readback(
    isolated_sql_settings: Settings,
    sql_connection: Any,
) -> None:
    settings = isolated_sql_settings
    fetcher = UsedCarFetcher(
        client=ApiClient(settings),
        interval_seconds=settings.interval_seconds,
    )
    try:
        pages = list(fetcher.iter_initial(settings.batch_size, settings.max_batches))
        watermark = fetcher.incremental_watermark()
    finally:
        fetcher.close()
    prepared, rejected = transform_records(
        [record for page in pages for record in page.records],
        settings=settings,
        run_id="live-usedcar-source",
        dataset_epoch=watermark.get("dataset_epoch")
        or pages[0].meta.get("dataset_epoch"),
    )
    assert rejected == []
    assert prepared

    first_settings = replace(
        settings,
        state_path=settings.output_dir / "usedcar-first-checkpoint.json",
    )
    first = usedcar.run_once(
        settings=first_settings,
        mode="initial",
        sink_name="sql",
        run_id="live-usedcar-first",
    )
    first_pipeline_rows = _mysql_rows(
        sql_connection,
        "SELECT collected_count, preprocessed_count, valid_count, rejected_count, "
        "inserted_count, updated_count, unchanged_count, api_calls, progress_key "
        "FROM pipeline_runs WHERE pipeline_name='used_car'",
    )
    assert len(first_pipeline_rows) == first["batches"]
    assert 1 <= first["batches"] <= settings.max_batches
    assert tuple(
        sum(int(row[index]) for row in first_pipeline_rows) for index in range(8)
    ) == (
        first["collected_count"],
        first["preprocessed_count"],
        first["valid_count"],
        first["rejected_count"],
        first["inserted_count"],
        first["updated_count"],
        first["unchanged_count"],
        first["api_calls"],
    )
    progress = [json.loads(row[8]) for row in first_pipeline_rows if row[8]]
    assert len(progress) == 1
    assert progress[0]["after_seq"] == watermark["high_water_seq"]
    assert (
        json.loads(first_settings.state_path.read_text(encoding="utf-8"))["after_seq"]
        == watermark["high_water_seq"]
    )
    with sql_connection.cursor() as cursor:
        cursor.execute("DELETE FROM pipeline_runs WHERE pipeline_name='used_car'")
    sql_connection.commit()
    second_settings = replace(
        settings,
        state_path=settings.output_dir / "usedcar-second-checkpoint.json",
    )
    second = usedcar.run_once(
        settings=second_settings,
        mode="initial",
        sink_name="sql",
        run_id="live-usedcar-second",
    )
    assert first["collected_count"] == len(prepared)
    assert first["inserted_count"] == len(prepared)
    assert second["collected_count"] == len(prepared)
    assert second["unchanged_count"] == len(prepared)

    rows = _mysql_rows(
        sql_connection,
        "SELECT listing_id, content_hash FROM vehicle_listings ORDER BY listing_id",
    )
    stored = {str(row[0]): row[1] for row in rows}
    expected = {
        str(row["listing"]["listing_id"]): row["listing"]["content_hash"]
        for row in prepared
    }
    assert stored == expected

    original_raw = copy.deepcopy(pages[0].records[0])
    changed_raw = copy.deepcopy(original_raw)
    changed_raw["title"] = f"{changed_raw.get('title') or ''} [live update probe]"
    original = transform_record(
        original_raw,
        base_url=settings.base_url,
        run_id="live-usedcar-restore",
        collected_at=datetime.now(timezone.utc).isoformat(),
        dataset_epoch=watermark.get("dataset_epoch"),
    )
    changed = transform_record(
        changed_raw,
        base_url=settings.base_url,
        run_id="live-usedcar-update",
        collected_at=datetime.now(timezone.utc).isoformat(),
        dataset_epoch=watermark.get("dataset_epoch"),
    )
    sink = SqlUpsertSink(settings)
    try:
        unchanged = sink.save([original])
        updated = sink.save([changed])
        restored = sink.save([original])
        assert unchanged.unchanged_count == 1
        assert updated.updated_count == 1
        assert restored.updated_count == 1
    finally:
        sink.close()
    readback = _mysql_rows(
        sql_connection,
        "SELECT title, content_hash FROM vehicle_listings WHERE listing_id=%s",
        (original["listing"]["listing_id"],),
    )
    assert readback == [
        (original["listing"]["title"], original["listing"]["content_hash"])
    ]
    fk_orphans = _mysql_rows(
        sql_connection,
        "SELECT "
        "SUM(l.model_id IS NOT NULL AND m.model_id IS NULL), "
        "SUM(l.location_id IS NOT NULL AND loc.location_id IS NULL), "
        "SUM(l.dealer_code IS NOT NULL AND d.dealer_code IS NULL), "
        "SUM(l.business_area_id IS NOT NULL AND a.business_area_id IS NULL) "
        "FROM vehicle_listings l "
        "LEFT JOIN vehicle_models m ON m.model_id=l.model_id "
        "LEFT JOIN vehicle_locations loc ON loc.location_id=l.location_id "
        "LEFT JOIN vehicle_dealers d ON d.dealer_code=l.dealer_code "
        "LEFT JOIN vehicle_business_areas a ON a.business_area_id=l.business_area_id",
    )[0]
    assert fk_orphans == (0, 0, 0, 0)
    dimension_orphans = _mysql_rows(
        sql_connection,
        "SELECT "
        "(SELECT COUNT(*) FROM vehicle_models m LEFT JOIN vehicle_brands b "
        "ON b.brand_id=m.brand_id WHERE m.brand_id IS NOT NULL AND b.brand_id IS NULL), "
        "(SELECT COUNT(*) FROM vehicle_business_areas c "
        "LEFT JOIN vehicle_business_areas p "
        "ON p.business_area_id=c.parent_business_area_id "
        "WHERE c.parent_business_area_id IS NOT NULL AND p.business_area_id IS NULL)",
    )[0]
    assert dimension_orphans == (0, 0)


def test_live_usedcar_incremental_checkpoint_uses_processed_sequence_and_counts(
    isolated_sql_settings: Settings,
    sql_connection: Any,
) -> None:
    settings = isolated_sql_settings
    result = usedcar.run_once(
        settings=replace(
            settings,
            state_path=settings.output_dir / "usedcar-incremental-checkpoint.json",
        ),
        mode="incremental",
        sink_name="sql",
        run_id="live-usedcar-incremental",
    )
    assert 1 <= result["batches"] <= settings.max_batches
    assert result["collected_count"] > 0
    assert (
        result["preprocessed_count"] == result["valid_count"] + result["rejected_count"]
    )
    assert (
        result["inserted_count"] + result["updated_count"] + result["unchanged_count"]
        == result["valid_count"]
    )

    pipeline_rows = _mysql_rows(
        sql_connection,
        "SELECT collected_count, preprocessed_count, valid_count, rejected_count, "
        "inserted_count, updated_count, unchanged_count, api_calls, progress_key "
        "FROM pipeline_runs WHERE pipeline_name='used_car'",
    )
    assert len(pipeline_rows) == result["batches"]
    assert tuple(
        sum(int(row[index]) for row in pipeline_rows) for index in range(8)
    ) == (
        result["collected_count"],
        result["preprocessed_count"],
        result["valid_count"],
        result["rejected_count"],
        result["inserted_count"],
        result["updated_count"],
        result["unchanged_count"],
        result["api_calls"],
    )
    checkpoints = [json.loads(row[8]) for row in pipeline_rows]
    sequences = sorted(checkpoint["after_seq"] for checkpoint in checkpoints)
    assert sequences[0] > 0
    assert sequences == sorted(set(sequences))
    checkpoint = max(checkpoints, key=lambda item: item["after_seq"])

    client = ApiClient(settings)
    source_fetcher = UsedCarFetcher(client)
    try:
        source_pages = list(
            source_fetcher.iter_incremental(
                0, settings.batch_size, settings.max_batches
            )
        )
    finally:
        source_fetcher.close()
    source_states = [page_checkpoint(page.meta, page.records) for page in source_pages]
    assert checkpoint["after_seq"] == source_states[-1]["high_water_seq"]
    if source_states[-1].get("until_seq") is not None:
        assert checkpoint["after_seq"] <= source_states[-1]["until_seq"]
    listing_rows = _mysql_rows(
        sql_connection,
        "SELECT COUNT(*), COUNT(DISTINCT listing_id), MAX(source_sequence) FROM vehicle_listings",
    )[0]
    expected_listing_ids = {
        str(row["listing"]["listing_id"])
        for page in source_pages
        for row in transform_records(
            page.records,
            settings=settings,
            run_id="live-usedcar-id-evidence",
            dataset_epoch=page.meta.get("dataset_epoch"),
        )[0]
    }
    assert listing_rows[0] == listing_rows[1] == len(expected_listing_ids)
    assert listing_rows[0] <= result["valid_count"]
    valid_sequences = [
        row["listing"]["source_sequence"]
        for page in source_pages
        for row in transform_records(
            page.records,
            settings=settings,
            run_id="live-usedcar-sequence-evidence",
            dataset_epoch=page.meta.get("dataset_epoch"),
        )[0]
        if row["listing"]["source_sequence"] is not None
    ]
    assert listing_rows[2] == max(valid_sequences)
    assert listing_rows[2] <= checkpoint["after_seq"]


def test_live_usedcar_steady_state_and_sparse_merge_integrity(
    isolated_sql_settings: Settings,
    sql_connection: Any,
) -> None:
    settings = isolated_sql_settings
    client = ApiClient(settings)
    try:
        fetcher = UsedCarFetcher(client, interval_seconds=settings.interval_seconds)
        watermark = fetcher.incremental_watermark()
    finally:
        client.close()
    checkpoint_path = settings.output_dir / "usedcar-steady-state-checkpoint.json"
    checkpoint_path.write_text(
        json.dumps(
            {
                "initialized": True,
                "after_seq": watermark["high_water_seq"],
                "dataset_epoch": watermark.get("dataset_epoch"),
            }
        ),
        encoding="utf-8",
    )
    steady = usedcar.run_once(
        settings=replace(settings, state_path=checkpoint_path),
        mode="incremental",
        sink_name="sql",
        run_id="live-usedcar-steady-state",
    )
    assert steady["status"] == "OK"
    assert steady["preprocessed_count"] == (
        steady["valid_count"] + steady["rejected_count"]
    )
    assert (
        steady["inserted_count"] + steady["updated_count"] + steady["unchanged_count"]
        == steady["valid_count"]
    )
    persisted_seq = json.loads(checkpoint_path.read_text(encoding="utf-8"))["after_seq"]
    assert persisted_seq >= watermark["high_water_seq"]
    if steady["collected_count"] == 0:
        assert persisted_seq == watermark["high_water_seq"]

    source_client = ApiClient(settings)
    try:
        page = next(UsedCarFetcher(source_client).iter_initial(1, 1))
    finally:
        source_client.close()
    original = transform_record(
        page.records[0],
        base_url=settings.base_url,
        run_id="live-usedcar-sparse-original",
        collected_at=datetime.now(timezone.utc).isoformat(),
        dataset_epoch=watermark.get("dataset_epoch"),
    )
    sparse = transform_record(
        {
            "id": page.records[0]["id"],
            "title": f"{page.records[0].get('title') or ''} [sparse update probe]",
            "_event_id": "live-sparse-event",
            "_change_seq": watermark["high_water_seq"] + 1,
        },
        base_url=settings.base_url,
        run_id="live-usedcar-sparse-update",
        collected_at=datetime.now(timezone.utc).isoformat(),
        dataset_epoch=watermark.get("dataset_epoch"),
    )
    sink = SqlUpsertSink(settings)
    try:
        assert sink.save([original]).inserted_count == 1
        assert sink.save([sparse]).updated_count == 1
        event_only = copy.deepcopy(sparse)
        event_only["listing"]["source_event_id"] = "live-sparse-event-2"
        event_only["listing"]["source_sequence"] += 1
        assert sink.save([event_only]).unchanged_count == 1
    finally:
        sink.close()
    listing_id = original["listing"]["listing_id"]
    readback = _mysql_rows(
        sql_connection,
        "SELECT l.*, b.brand_id, b.name, b.slug, b.country, "
        "m.model_id, m.brand_id, m.name, m.slug, m.body_type, "
        "loc.location_id, loc.province, loc.city, loc.sigungu, loc.slug, "
        "d.dealer_code, d.display_name, d.department, d.position, "
        "a.business_area_id, a.name, a.slug, a.parent_business_area_id, "
        "pa.business_area_id, pa.name, pa.slug "
        "FROM vehicle_listings l "
        "LEFT JOIN vehicle_models m ON m.model_id=l.model_id "
        "LEFT JOIN vehicle_brands b ON b.brand_id=m.brand_id "
        "LEFT JOIN vehicle_locations loc ON loc.location_id=l.location_id "
        "LEFT JOIN vehicle_dealers d ON d.dealer_code=l.dealer_code "
        "LEFT JOIN vehicle_business_areas a ON a.business_area_id=l.business_area_id "
        "LEFT JOIN vehicle_business_areas pa "
        "ON pa.business_area_id=a.parent_business_area_id "
        "WHERE l.listing_id=%s",
        (listing_id,),
    )
    assert len(readback) == 1
    columns = [
        "listing_id",
        "listing_number",
        "title",
        "description",
        "trim",
        "model_id",
        "location_id",
        "dealer_code",
        "business_area_id",
        "model_year",
        "first_registration",
        "mileage_km",
        "price_krw",
        "currency",
        "source_status",
        "fuel_type",
        "transmission",
        "color",
        "displacement_cc",
        "accident_count",
        "owner_change_count",
        "inspection_status",
        "source_event_id",
        "source_sequence",
        "content_hash",
        "source_url",
        "source_created_at",
        "source_updated_at",
        "run_id",
        "collected_at",
        "created_at",
        "updated_at",
    ]
    row = readback[0]
    listing = dict(zip(columns, row[: len(columns)]))
    offset = len(columns)
    aggregate = {
        "listing": listing,
        "brand": dict(
            zip(("brand_id", "name", "slug", "country"), row[offset : offset + 4])
        ),
        "model": dict(
            zip(
                ("model_id", "brand_id", "name", "slug", "body_type"),
                row[offset + 4 : offset + 9],
            )
        ),
        "location": dict(
            zip(
                ("location_id", "province", "city", "sigungu", "slug"),
                row[offset + 9 : offset + 14],
            )
        ),
        "dealer": dict(
            zip(
                ("dealer_code", "display_name", "department", "position"),
                row[offset + 14 : offset + 18],
            )
        ),
        "business_area": dict(
            zip(
                ("business_area_id", "name", "slug", "parent_business_area_id"),
                row[offset + 18 : offset + 22],
            )
        ),
    }
    parent = dict(
        zip(
            ("business_area_id", "name", "slug"),
            row[offset + 22 : offset + 25],
        )
    )
    if parent["business_area_id"] is not None:
        aggregate["business_area"]["parent"] = parent
    assert listing["description"] == original["listing"]["description"]
    assert listing["content_hash"] == usedcar_content_hash(aggregate)

    shared_first = copy.deepcopy(original)
    shared_first["listing"]["listing_id"] = "live-shared-model-a"
    shared_first["listing"]["listing_number"] = "LIVE-SHARED-A"
    shared_first["listing"]["title"] = "Shared model A"
    shared_first["listing"]["content_hash"] = usedcar_content_hash(shared_first)
    shared_second = copy.deepcopy(original)
    shared_second["listing"]["listing_id"] = "live-shared-model-b"
    shared_second["listing"]["listing_number"] = "LIVE-SHARED-B"
    shared_second["listing"]["title"] = "Shared model B"
    shared_second["listing"]["content_hash"] = usedcar_content_hash(shared_second)
    changed_shared = copy.deepcopy(shared_first)
    changed_shared["model"]["name"] = "Live shared model update probe"

    sink = SqlUpsertSink(settings)
    try:
        assert sink.save([shared_first, shared_second]).inserted_count == 2
        assert sink.save([changed_shared]) == LoadStats(updated_count=1)
    finally:
        sink.close()
    sql_connection.rollback()
    expected_first = copy.deepcopy(shared_first)
    expected_first["model"] = changed_shared["model"]
    expected_second = copy.deepcopy(shared_second)
    expected_second["model"] = changed_shared["model"]
    shared_rows = _mysql_rows(
        sql_connection,
        "SELECT l.listing_id, l.content_hash, m.name "
        "FROM vehicle_listings l "
        "JOIN vehicle_models m ON m.model_id=l.model_id "
        "WHERE l.listing_id IN (%s, %s) ORDER BY l.listing_id",
        ("live-shared-model-a", "live-shared-model-b"),
    )
    assert shared_rows == [
        (
            "live-shared-model-a",
            usedcar_content_hash(expected_first),
            "Live shared model update probe",
        ),
        (
            "live-shared-model-b",
            usedcar_content_hash(expected_second),
            "Live shared model update probe",
        ),
    ]


def test_live_registration_detail_only_upsert_and_readback_integrity(
    registration_sql_settings: Settings,
    sql_connection: Any,
) -> None:
    period = "2026-06"
    settings = registration_sql_settings
    raw = _registration_raw(settings, period)
    prepared, rejected = transform_registration_records(
        raw,
        period=period,
        settings=settings,
        run_id="live-registration-source",
        collected_at=datetime.now(timezone.utc).isoformat(),
    )
    assert rejected == []
    assert raw
    expected_detail_count = _detail_measure_count(raw)
    assert expected_detail_count > 0
    assert len(prepared) == expected_detail_count
    assert not any(
        row["vehicle_type"] == "총계" or row["usage_type"] == "계" for row in prepared
    )

    first = registration.run_once(
        settings=settings,
        sink_name="sql",
        period=period,
        run_id="live-registration-first",
    )
    second = registration.run_once(
        settings=settings,
        sink_name="sql",
        period=period,
        run_id="live-registration-second",
    )
    assert first["collected_count"] == len(raw)
    assert first["preprocessed_count"] == len(prepared)
    assert first["inserted_count"] == len(prepared)
    assert second["unchanged_count"] == len(prepared)
    assert first["api_calls"] >= 1 and second["api_calls"] >= 1

    counts = _mysql_rows(
        sql_connection,
        "SELECT COUNT(*), COUNT(DISTINCT report_month, sido_name, sigungu_name, vehicle_type, usage_type), "
        "SUM(vehicle_type='총계'), SUM(usage_type='계') FROM vehicle_registration_reports",
    )[0]
    assert counts == (len(prepared), len(prepared), 0, 0)
    stored = _mysql_rows(
        sql_connection,
        "SELECT report_month, sido_name, sigungu_name, vehicle_type, usage_type, quantity, content_hash "
        "FROM vehicle_registration_reports",
    )
    expected = {
        (
            row["report_month"],
            row["sido_name"],
            row["sigungu_name"],
            row["vehicle_type"],
            row["usage_type"],
        ): (row["quantity"], row["content_hash"])
        for row in prepared
    }
    actual = {
        (
            row[0].isoformat(),
            row[1],
            row[2],
            row[3],
            row[4],
        ): (row[5], row[6])
        for row in stored
    }
    assert actual == expected


def test_live_registration_changed_detail_updates_without_duplicate(
    registration_sql_settings: Settings,
    sql_connection: Any,
) -> None:
    period = "2026-06"
    settings = registration_sql_settings
    raw = _registration_raw(settings, period)
    original_rows, rejected = transform_registration_records(
        [raw[0]],
        period=period,
        settings=settings,
        run_id="live-registration-original",
        collected_at=datetime.now(timezone.utc).isoformat(),
    )
    assert rejected == []
    assert len(original_rows) == _detail_measure_count([raw[0]]) > 0
    source = copy.deepcopy(raw[0])
    target = original_rows[0]
    source_key = f"{target['vehicle_type']}>{target['usage_type']}"
    source[source_key] = int(target["quantity"] or 0) + 1
    changed_rows, changed_rejected = transform_registration_records(
        [source],
        period=period,
        settings=settings,
        run_id="live-registration-changed",
        collected_at=datetime.now(timezone.utc).isoformat(),
    )
    assert changed_rejected == []

    sink = SqlRegistrationUpsertSink(settings)
    try:
        inserted = sink.save(original_rows)
        unchanged = sink.save(original_rows)
        updated = sink.save(changed_rows)
        restored = sink.save(original_rows)
        expected_count = len(original_rows)
        assert inserted.inserted_count == expected_count
        assert unchanged.unchanged_count == expected_count
        assert updated.updated_count == 1
        assert updated.unchanged_count == expected_count - 1
        assert restored.updated_count == 1
        assert restored.unchanged_count == expected_count - 1
    finally:
        sink.close()
    counts = _mysql_rows(
        sql_connection,
        "SELECT COUNT(*), COUNT(DISTINCT report_month, sido_name, sigungu_name, vehicle_type, usage_type) "
        "FROM vehicle_registration_reports",
    )[0]
    assert counts == (len(original_rows), len(original_rows))
