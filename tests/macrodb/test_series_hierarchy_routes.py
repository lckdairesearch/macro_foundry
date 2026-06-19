"""Coverage for canonical series hierarchy routes."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from http import HTTPStatus

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from macro_foundry.enums import (
    Frequency,
    Measure,
    OriginType,
    SeasonalAdjustment,
    TemporalStockFlow,
    UnitKind,
    UnitScale,
)
from macro_foundry.models import Geography, Observation, Series


async def _seeded_country(session: AsyncSession, *, code: str = "USA") -> Geography:
    geography = await session.scalar(select(Geography).where(Geography.code == code))
    assert geography is not None
    return geography


async def _create_series(
    session: AsyncSession,
    *,
    code: str,
    geography: Geography,
) -> Series:
    series = Series(
        code=code,
        name=f"{code} name",
        origin_type=OriginType.INGESTED,
        geography_id=geography.id,
        frequency=Frequency.MONTHLY,
        temporal_stock_flow=TemporalStockFlow.INDEX,
        unit_kind=UnitKind.INDEX,
        unit_scale=UnitScale.ONE,
        measure=Measure.LEVEL,
        annualized=False,
        seasonal_adjustment=SeasonalAdjustment.NSA,
        is_active=True,
    )
    session.add(series)
    await session.flush()
    return series


@pytest.mark.asyncio
async def test_create_series_hierarchy_edge_links_real_series(
    client: AsyncClient,
    session: AsyncSession,
    auth_headers: dict[str, str],
) -> None:
    geography = await _seeded_country(session)
    parent = await _create_series(session, code="US_CPI_PARENT", geography=geography)
    child = await _create_series(session, code="US_CPI_CHILD", geography=geography)
    await session.commit()

    response = await client.post(
        "/api/v1/series-hierarchy-edges/",
        headers=auth_headers,
        json={
            "parent_series_id": str(parent.id),
            "child_series_id": str(child.id),
            "sort_order": 1,
            "notes": "Headline to child item",
        },
    )

    assert response.status_code == HTTPStatus.CREATED
    created = response.json()
    assert created["parent_series_id"] == str(parent.id)
    assert created["child_series_id"] == str(child.id)

    list_response = await client.get(
        f"/api/v1/series-hierarchy-edges/?parent_series_id={parent.id}",
        headers=auth_headers,
    )

    assert list_response.status_code == HTTPStatus.OK
    assert [row["child_series_id"] for row in list_response.json()] == [str(child.id)]


@pytest.mark.asyncio
async def test_series_hierarchy_supports_ragged_additive_children_without_replacing_parent_observations(
    client: AsyncClient,
    session: AsyncSession,
    auth_headers: dict[str, str],
) -> None:
    geography = await _seeded_country(session)
    parent = await _create_series(session, code="US_CPI_RAGGED_PARENT", geography=geography)
    child = await _create_series(session, code="US_CPI_RAGGED_CHILD", geography=geography)
    grandchild = await _create_series(session, code="US_CPI_RAGGED_GRANDCHILD", geography=geography)

    parent_observation = Observation(
        series_id=parent.id,
        period_start=date(2026, 1, 1),
        period_end=date(2026, 1, 31),
        value=Decimal("301.2"),
        vintage_date=date(2026, 2, 15),
    )
    session.add(parent_observation)
    await session.commit()

    parent_child_response = await client.post(
        "/api/v1/series-hierarchy-edges/",
        headers=auth_headers,
        json={
            "parent_series_id": str(parent.id),
            "child_series_id": str(child.id),
            "sort_order": 1,
        },
    )
    child_grandchild_response = await client.post(
        "/api/v1/series-hierarchy-edges/",
        headers=auth_headers,
        json={
            "parent_series_id": str(child.id),
            "child_series_id": str(grandchild.id),
            "sort_order": 1,
        },
    )

    assert parent_child_response.status_code == HTTPStatus.CREATED
    assert child_grandchild_response.status_code == HTTPStatus.CREATED

    parent_children = await client.get(
        f"/api/v1/series-hierarchy-edges/?parent_series_id={parent.id}",
        headers=auth_headers,
    )
    child_children = await client.get(
        f"/api/v1/series-hierarchy-edges/?parent_series_id={child.id}",
        headers=auth_headers,
    )

    assert [row["child_series_id"] for row in parent_children.json()] == [str(child.id)]
    assert [row["child_series_id"] for row in child_children.json()] == [str(grandchild.id)]

    stored_parent_observation = await session.scalar(
        select(Observation).where(Observation.series_id == parent.id),
    )
    assert stored_parent_observation is not None
    assert stored_parent_observation.value == Decimal("301.2")


@pytest.mark.asyncio
async def test_series_hierarchy_rejects_hidden_placeholder_nodes(
    client: AsyncClient,
    session: AsyncSession,
    auth_headers: dict[str, str],
) -> None:
    geography = await _seeded_country(session)
    parent = await _create_series(session, code="US_CPI_NO_PLACEHOLDER_PARENT", geography=geography)
    child = await _create_series(session, code="US_CPI_NO_PLACEHOLDER_CHILD", geography=geography)
    await session.commit()

    response = await client.post(
        "/api/v1/series-hierarchy-edges/",
        headers=auth_headers,
        json={
            "parent_series_id": str(parent.id),
            "child_series_id": str(child.id),
            "child_placeholder_label": "Provider indentation group",
        },
    )

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
