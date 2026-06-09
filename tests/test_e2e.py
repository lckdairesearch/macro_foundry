"""Phase 12 end-to-end smoke coverage."""

from __future__ import annotations

from http import HTTPStatus

import pytest
from httpx import AsyncClient

from macro_foundry.enums import (
    FeedMethod,
    Frequency,
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
            "family_id": family_id,
            "series_id": series_id,
            "variant": "Headline NSA",
            "is_primary": True,
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
