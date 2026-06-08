"""Focused Phase 10 coverage for hand-written series routes."""

from __future__ import annotations

from http import HTTPStatus

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from macro_foundry.enums import (
    CodeStandard,
    Frequency,
    GeographyType,
    Measure,
    MeasureHorizon,
    OriginType,
    SeasonalAdjustment,
    TemporalStockFlow,
    UnitKind,
    UnitScale,
)
from macro_foundry.models import Geography, Series, SeriesTag, Tag


async def _create_country(session: AsyncSession, *, code: str = "USA", name: str = "United States") -> Geography:
    existing = await session.scalar(select(Geography).where(Geography.code == code))
    if existing is not None:
        return existing

    geography = Geography(
        code=code,
        name=name,
        type=GeographyType.COUNTRY,
        code_standard=CodeStandard.ISO_3166_1,
    )
    session.add(geography)
    await session.commit()
    await session.refresh(geography)
    return geography


async def _create_series(
    session: AsyncSession,
    geography: Geography,
    *,
    code: str = "US_CPI",
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
    await session.commit()
    await session.refresh(series)
    return series


@pytest.mark.asyncio
async def test_create_series_persists_valid_payload(
    client: AsyncClient,
    session: AsyncSession,
    auth_headers: dict[str, str],
) -> None:
    geography = await _create_country(session)

    response = await client.post(
        "/api/v1/series/",
        headers=auth_headers,
        json={
            "code": "US_CPI_YOY",
            "name": "US CPI YoY",
            "origin_type": OriginType.INGESTED.value,
            "geography_id": str(geography.id),
            "frequency": Frequency.MONTHLY.value,
            "temporal_stock_flow": TemporalStockFlow.INDEX.value,
            "unit_kind": UnitKind.PERCENT.value,
            "unit_scale": UnitScale.ONE.value,
            "measure": Measure.GROWTH.value,
            "measure_horizon": MeasureHorizon.YOY.value,
            "annualized": False,
            "seasonal_adjustment": SeasonalAdjustment.NSA.value,
            "is_active": True,
        },
    )

    assert response.status_code == HTTPStatus.CREATED
    assert response.json()["code"] == "US_CPI_YOY"

    stored = await session.scalar(select(Series).where(Series.code == "US_CPI_YOY"))
    assert stored is not None


@pytest.mark.asyncio
async def test_create_series_rejects_growth_without_horizon(
    client: AsyncClient,
    session: AsyncSession,
    auth_headers: dict[str, str],
) -> None:
    geography = await _create_country(session)

    response = await client.post(
        "/api/v1/series/",
        headers=auth_headers,
        json={
            "code": "US_BAD_GROWTH",
            "name": "US bad growth",
            "origin_type": OriginType.INGESTED.value,
            "geography_id": str(geography.id),
            "frequency": Frequency.MONTHLY.value,
            "temporal_stock_flow": TemporalStockFlow.INDEX.value,
            "unit_kind": UnitKind.PERCENT.value,
            "unit_scale": UnitScale.ONE.value,
            "measure": Measure.GROWTH.value,
            "annualized": False,
            "seasonal_adjustment": SeasonalAdjustment.NSA.value,
            "is_active": True,
        },
    )

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


@pytest.mark.asyncio
async def test_patch_series_revalidates_merged_state(
    client: AsyncClient,
    session: AsyncSession,
    auth_headers: dict[str, str],
) -> None:
    geography = await _create_country(session)
    series = await _create_series(session, geography)

    response = await client.patch(
        f"/api/v1/series/{series.id}",
        headers=auth_headers,
        json={"measure": Measure.GROWTH.value},
    )

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


@pytest.mark.asyncio
async def test_patch_series_rejects_duplicate_code(
    client: AsyncClient,
    session: AsyncSession,
    auth_headers: dict[str, str],
) -> None:
    geography = await _create_country(session)
    first_series = await _create_series(session, geography, code="US_CPI")
    second_series = await _create_series(session, geography, code="US_CORE_CPI")

    response = await client.patch(
        f"/api/v1/series/{second_series.id}",
        headers=auth_headers,
        json={"code": first_series.code},
    )

    assert response.status_code == HTTPStatus.CONFLICT
    assert "already exists" in response.json()["detail"]


@pytest.mark.asyncio
async def test_get_series_returns_geography_and_tags(
    client: AsyncClient,
    session: AsyncSession,
    auth_headers: dict[str, str],
) -> None:
    geography = await _create_country(session)
    series = await _create_series(session, geography)
    tag = Tag(name="inflation")
    session.add(tag)
    await session.flush()
    session.add(SeriesTag(series_id=series.id, tag_id=tag.id))
    await session.commit()

    response = await client.get(f"/api/v1/series/{series.id}", headers=auth_headers)

    assert response.status_code == HTTPStatus.OK
    payload = response.json()
    assert payload["geography"]["code"] == geography.code
    assert [tag_payload["name"] for tag_payload in payload["tags"]] == ["inflation"]
