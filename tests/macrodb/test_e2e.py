"""Phase 12 end-to-end smoke coverage."""

from __future__ import annotations

from http import HTTPStatus

import pytest
from httpx import AsyncClient

from macro_foundry.enums import (
    FeedMethod,
    Frequency,
    IngestionRunStatus,
    IngestionTriggeredBy,
    Measure,
    OriginType,
    ProviderRole,
    SeasonalAdjustment,
    TemporalStockFlow,
    UnitKind,
    UnitScale,
)


@pytest.mark.asyncio
async def test_api_smoke_flows_from_seeded_geography_to_observations(
    client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    geography_response = await client.get(
        "/api/v1/geographies/",
        headers=auth_headers,
        params={"code": "USA"},
    )
    assert geography_response.status_code == HTTPStatus.OK
    geography_id = geography_response.json()[0]["id"]

    concept_response = await client.post(
        "/api/v1/concepts/",
        headers=auth_headers,
        json={"code": "MF_E2E_CPI", "name": "Macro Foundry E2E CPI"},
    )
    assert concept_response.status_code == HTTPStatus.CREATED
    concept_id = concept_response.json()["id"]

    family_response = await client.post(
        "/api/v1/series-families/",
        headers=auth_headers,
        json={
            "code": "MF_US_CPI_FAMILY",
            "name": "Macro Foundry US CPI family",
            "concept_id": concept_id,
            "geography_id": geography_id,
        },
    )
    assert family_response.status_code == HTTPStatus.CREATED
    family_id = family_response.json()["id"]

    tag_response = await client.post(
        "/api/v1/tags/",
        headers=auth_headers,
        json={"name": "macro_foundry_smoke"},
    )
    assert tag_response.status_code == HTTPStatus.CREATED
    tag_id = tag_response.json()["id"]

    series_response = await client.post(
        "/api/v1/series/",
        headers=auth_headers,
        json={
            "code": "MF_US_CPI_SERIES",
            "name": "Macro Foundry US CPI series",
            "origin_type": OriginType.INGESTED.value,
            "geography_id": geography_id,
            "frequency": Frequency.MONTHLY.value,
            "temporal_stock_flow": TemporalStockFlow.INDEX.value,
            "unit_kind": UnitKind.INDEX.value,
            "unit_scale": UnitScale.ONE.value,
            "measure": Measure.LEVEL.value,
            "annualized": False,
            "seasonal_adjustment": SeasonalAdjustment.NSA.value,
            "is_active": True,
        },
    )
    assert series_response.status_code == HTTPStatus.CREATED
    series_id = series_response.json()["id"]

    family_member_response = await client.post(
        "/api/v1/series-family-members/",
        headers=auth_headers,
        json={
            "indicator_id": family_id,
            "series_id": series_id,
            "label": "Headline NSA",
            "is_default": True,
        },
    )
    assert family_member_response.status_code == HTTPStatus.CREATED

    series_tag_response = await client.post(
        "/api/v1/series-tags/",
        headers=auth_headers,
        json={
            "series_id": series_id,
            "tag_id": tag_id,
        },
    )
    assert series_tag_response.status_code == HTTPStatus.CREATED

    series_detail_response = await client.get(f"/api/v1/series/{series_id}", headers=auth_headers)
    assert series_detail_response.status_code == HTTPStatus.OK
    series_detail = series_detail_response.json()
    assert series_detail["geography"]["code"] == "USA"
    assert [tag["name"] for tag in series_detail["tags"]] == ["macro_foundry_smoke"]

    bulk_response = await client.post(
        "/api/v1/observations/bulk",
        headers=auth_headers,
        json=[
            {
                "series_id": series_id,
                "period_start": "2026-01-01",
                "period_end": "2026-01-31",
                "value": "100.0",
                "vintage_date": "2026-02-15",
            },
            {
                "series_id": series_id,
                "period_start": "2026-02-01",
                "period_end": "2026-02-28",
                "value": "101.0",
                "vintage_date": "2026-03-15",
            },
        ],
    )
    assert bulk_response.status_code == HTTPStatus.OK
    assert bulk_response.json()["inserted"] == 2

    observation_response = await client.get(
        "/api/v1/observations/",
        headers=auth_headers,
        params={"series_id": series_id},
    )
    assert observation_response.status_code == HTTPStatus.OK
    assert [row["period_start"] for row in observation_response.json()] == [
        "2026-01-01",
        "2026-02-01",
    ]


@pytest.mark.asyncio
async def test_api_catalog_supports_shared_ingestion_feed_members(
    client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    geography_response = await client.get(
        "/api/v1/geographies/",
        headers=auth_headers,
        params={"code": "USA"},
    )
    assert geography_response.status_code == HTTPStatus.OK
    geography_id = geography_response.json()[0]["id"]

    catalog_response = await client.get(
        "/api/v1/provider-catalogs/",
        headers=auth_headers,
        params={"name": "FRED default catalog"},
    )
    assert catalog_response.status_code == HTTPStatus.OK
    catalog_id = catalog_response.json()[0]["id"]

    series_ids = []
    for suffix in ("A", "B"):
        series_response = await client.post(
            "/api/v1/series/",
            headers=auth_headers,
            json={
                "code": f"MF_SHARED_FEED_{suffix}",
                "name": f"Macro Foundry shared feed series {suffix}",
                "origin_type": OriginType.INGESTED.value,
                "geography_id": geography_id,
                "frequency": Frequency.MONTHLY.value,
                "temporal_stock_flow": TemporalStockFlow.INDEX.value,
                "unit_kind": UnitKind.INDEX.value,
                "unit_scale": UnitScale.ONE.value,
                "measure": Measure.LEVEL.value,
                "annualized": False,
                "seasonal_adjustment": SeasonalAdjustment.NSA.value,
                "is_active": True,
            },
        )
        assert series_response.status_code == HTTPStatus.CREATED
        series_ids.append(series_response.json()["id"])

    source_ids = []
    for suffix, series_id in zip(("A", "B"), series_ids, strict=True):
        source_response = await client.post(
            "/api/v1/series-sources/",
            headers=auth_headers,
            json={
                "series_id": series_id,
                "provider_catalog_id": catalog_id,
                "external_name": f"Shared feed source {suffix}",
                "ref_url": f"https://example.test/shared#{suffix.lower()}",
                "priority": 1,
                "provider_role": ProviderRole.PRIMARY_SOURCE.value,
            },
        )
        assert source_response.status_code == HTTPStatus.CREATED
        source_ids.append(source_response.json()["id"])

    feed_response = await client.post(
        "/api/v1/ingestion-feeds/",
        headers=auth_headers,
        json={
            "feed_method": FeedMethod.API.value,
            "endpoint_url": "/shared/table",
            "request_params": {"table": "shared"},
            "response_mapping": {"data_path": "rows"},
            "is_active": True,
        },
    )
    assert feed_response.status_code == HTTPStatus.CREATED
    feed_id = feed_response.json()["id"]

    for order, source_id in enumerate(source_ids, start=1):
        member_response = await client.post(
            "/api/v1/ingestion-feed-members/",
            headers=auth_headers,
            json={
                "ingestion_feed_id": feed_id,
                "series_source_id": source_id,
                "selector_type": "json_path",
                "selector_config": {"path": f"$.rows[{order - 1}].value"},
                "execution_order": order,
                "is_active": True,
            },
        )
        assert member_response.status_code == HTTPStatus.CREATED

    member_list_response = await client.get(
        "/api/v1/ingestion-feed-members/",
        headers=auth_headers,
        params={"ingestion_feed_id": feed_id},
    )
    assert member_list_response.status_code == HTTPStatus.OK
    members = member_list_response.json()
    assert [member["series_source_id"] for member in members] == source_ids


@pytest.mark.asyncio
async def test_api_records_shared_feed_execution_with_member_outcomes(
    client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    geography_response = await client.get(
        "/api/v1/geographies/",
        headers=auth_headers,
        params={"code": "USA"},
    )
    assert geography_response.status_code == HTTPStatus.OK
    geography_id = geography_response.json()[0]["id"]

    catalog_response = await client.get(
        "/api/v1/provider-catalogs/",
        headers=auth_headers,
        params={"name": "FRED default catalog"},
    )
    assert catalog_response.status_code == HTTPStatus.OK
    catalog_id = catalog_response.json()[0]["id"]

    feed_response = await client.post(
        "/api/v1/ingestion-feeds/",
        headers=auth_headers,
        json={
            "feed_method": FeedMethod.API.value,
            "endpoint_url": "/shared/execution",
            "request_params": {"table": "member-outcomes"},
            "response_mapping": {"data_path": "rows"},
            "is_active": True,
        },
    )
    assert feed_response.status_code == HTTPStatus.CREATED
    feed_id = feed_response.json()["id"]

    series_ids = []
    member_ids = []
    for order, suffix in enumerate(("SUCCESS", "ZERO_WRITE", "FAILED"), start=1):
        series_response = await client.post(
            "/api/v1/series/",
            headers=auth_headers,
            json={
                "code": f"MF_SHARED_RUN_{suffix}",
                "name": f"Macro Foundry shared run {suffix.lower()}",
                "origin_type": OriginType.INGESTED.value,
                "geography_id": geography_id,
                "frequency": Frequency.MONTHLY.value,
                "temporal_stock_flow": TemporalStockFlow.INDEX.value,
                "unit_kind": UnitKind.INDEX.value,
                "unit_scale": UnitScale.ONE.value,
                "measure": Measure.LEVEL.value,
                "annualized": False,
                "seasonal_adjustment": SeasonalAdjustment.NSA.value,
                "is_active": True,
            },
        )
        assert series_response.status_code == HTTPStatus.CREATED
        series_ids.append(series_response.json()["id"])

        source_response = await client.post(
            "/api/v1/series-sources/",
            headers=auth_headers,
            json={
                "series_id": series_response.json()["id"],
                "provider_catalog_id": catalog_id,
                "external_name": f"Shared run source {suffix.lower()}",
                "priority": 1,
                "provider_role": ProviderRole.PRIMARY_SOURCE.value,
            },
        )
        assert source_response.status_code == HTTPStatus.CREATED

        member_response = await client.post(
            "/api/v1/ingestion-feed-members/",
            headers=auth_headers,
            json={
                "ingestion_feed_id": feed_id,
                "series_source_id": source_response.json()["id"],
                "selector_type": "json_path",
                "selector_config": {"path": f"$.rows[{order - 1}]"},
                "execution_order": order,
                "is_active": True,
            },
        )
        assert member_response.status_code == HTTPStatus.CREATED
        member_ids.append(member_response.json()["id"])

    run_response = await client.post(
        "/api/v1/ingestion-run-logs/",
        headers=auth_headers,
        json={
            "ingestion_feed_id": feed_id,
            "started_at": "2026-06-09T01:00:00Z",
            "finished_at": "2026-06-09T01:00:03Z",
            "status": IngestionRunStatus.PARTIAL.value,
            "rows_fetched": 12,
            "rows_inserted": 4,
            "rows_skipped": 8,
            "triggered_by": IngestionTriggeredBy.MANUAL.value,
            "parameters": {"date_from": "2026-01-01"},
        },
    )
    assert run_response.status_code == HTTPStatus.CREATED
    run_id = run_response.json()["id"]

    outcomes = [
        {
            "ingestion_run_log_id": run_id,
            "ingestion_feed_member_id": member_ids[0],
            "status": IngestionRunStatus.SUCCESS.value,
            "rows_fetched": 6,
            "rows_inserted": 4,
            "rows_skipped": 2,
        },
        {
            "ingestion_run_log_id": run_id,
            "ingestion_feed_member_id": member_ids[1],
            "status": IngestionRunStatus.SUCCESS.value,
            "rows_fetched": 4,
            "rows_inserted": 0,
            "rows_skipped": 4,
            "notes": "No changed rows.",
        },
        {
            "ingestion_run_log_id": run_id,
            "ingestion_feed_member_id": member_ids[2],
            "status": IngestionRunStatus.FAILED.value,
            "rows_fetched": 2,
            "rows_inserted": 0,
            "rows_skipped": 0,
            "error_message": "Member selector did not match a value.",
            "diagnostics": {"selector": "$.rows[2]", "reason": "missing"},
        },
    ]
    member_log_ids = []
    for outcome in outcomes:
        outcome_response = await client.post(
            "/api/v1/ingestion-run-log-members/",
            headers=auth_headers,
            json=outcome,
        )
        assert outcome_response.status_code == HTTPStatus.CREATED
        member_log_ids.append(outcome_response.json()["id"])

    member_log_response = await client.get(
        "/api/v1/ingestion-run-log-members/",
        headers=auth_headers,
        params={"ingestion_run_log_id": run_id},
    )
    assert member_log_response.status_code == HTTPStatus.OK
    member_logs = member_log_response.json()
    assert [member_log["ingestion_feed_member_id"] for member_log in member_logs] == member_ids
    assert [member_log["status"] for member_log in member_logs] == [
        IngestionRunStatus.SUCCESS.value,
        IngestionRunStatus.SUCCESS.value,
        IngestionRunStatus.FAILED.value,
    ]
    assert member_logs[1]["rows_inserted"] == 0
    assert member_logs[2]["diagnostics"] == {"selector": "$.rows[2]", "reason": "missing"}

    observation_response = await client.post(
        "/api/v1/observations/bulk",
        headers=auth_headers,
        json=[
            {
                "series_id": series_ids[0],
                "period_start": "2026-01-01",
                "period_end": "2026-01-31",
                "value": "100.0",
                "vintage_date": "2026-02-15",
                "ingestion_run_log_member_id": member_log_ids[0],
            },
        ],
    )
    assert observation_response.status_code == HTTPStatus.OK
    assert observation_response.json()["inserted"] == 1

    stored_observations_response = await client.get(
        "/api/v1/observations/",
        headers=auth_headers,
        params={"series_id": series_ids[0]},
    )
    assert stored_observations_response.status_code == HTTPStatus.OK
    stored_observations = stored_observations_response.json()
    assert stored_observations[0]["ingestion_run_log_member_id"] == member_log_ids[0]
