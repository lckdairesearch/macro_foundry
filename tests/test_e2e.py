"""Phase 12 end-to-end smoke coverage."""

from __future__ import annotations

from http import HTTPStatus

import pytest
from httpx import AsyncClient

from macro_foundry.enums import Frequency, Measure, OriginType, SeasonalAdjustment, TemporalStockFlow, UnitKind, UnitScale


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
