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
from macro_foundry.models import Concept, Geography, Observation, Series, Indicator, IndicatorVariant


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


async def _create_family_member(
    session: AsyncSession,
    *,
    concept_code: str,
    family_code: str,
    series: Series,
    geography: Geography,
) -> None:
    concept = await session.scalar(select(Concept).where(Concept.code == concept_code))
    if concept is None:
        concept = Concept(code=concept_code, name=f"{concept_code} concept")
        session.add(concept)
        await session.flush()

    family = Indicator(
        code=family_code,
        name=f"{family_code} family",
        concept_id=concept.id,
        geography_id=geography.id,
    )
    session.add(family)
    await session.flush()

    session.add(
        IndicatorVariant(
            indicator_id=family.id,
            series_id=series.id,
            label=series.code,
            is_default=False,
        ),
    )


@pytest.mark.asyncio
async def test_create_series_hierarchy_edge_links_real_same_concept_series(
    client: AsyncClient,
    session: AsyncSession,
    auth_headers: dict[str, str],
) -> None:
    geography = await _seeded_country(session)
    parent = await _create_series(session, code="US_CPI_PARENT", geography=geography)
    child = await _create_series(session, code="US_CPI_CHILD", geography=geography)
    await _create_family_member(
        session,
        concept_code="MF_HIERARCHY_CPI",
        family_code="US_CPI_PARENT_FAMILY",
        series=parent,
        geography=geography,
    )
    await _create_family_member(
        session,
        concept_code="MF_HIERARCHY_CPI",
        family_code="US_CPI_CHILD_FAMILY",
        series=child,
        geography=geography,
    )
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
async def test_create_series_hierarchy_edge_rejects_cross_concept_edges(
    client: AsyncClient,
    session: AsyncSession,
    auth_headers: dict[str, str],
) -> None:
    geography = await _seeded_country(session)
    parent = await _create_series(session, code="US_RETAIL_PARENT", geography=geography)
    child = await _create_series(session, code="US_CPI_WRONG_CONCEPT_CHILD", geography=geography)
    await _create_family_member(
        session,
        concept_code="MF_HIERARCHY_RETAIL",
        family_code="US_RETAIL_PARENT_FAMILY",
        series=parent,
        geography=geography,
    )
    await _create_family_member(
        session,
        concept_code="MF_HIERARCHY_CPI",
        family_code="US_CPI_WRONG_CONCEPT_CHILD_FAMILY",
        series=child,
        geography=geography,
    )
    await session.commit()

    response = await client.post(
        "/api/v1/series-hierarchy-edges/",
        headers=auth_headers,
        json={
            "parent_series_id": str(parent.id),
            "child_series_id": str(child.id),
        },
    )

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert "one concept" in response.json()["detail"]


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
    for series in (parent, child, grandchild):
        await _create_family_member(
            session,
            concept_code="MF_HIERARCHY_RAGGED_CPI",
            family_code=f"{series.code}_FAMILY",
            series=series,
            geography=geography,
        )

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
    for series in (parent, child):
        await _create_family_member(
            session,
            concept_code="MF_HIERARCHY_NO_PLACEHOLDER_CPI",
            family_code=f"{series.code}_FAMILY",
            series=series,
            geography=geography,
        )
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
