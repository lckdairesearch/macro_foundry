"""Focused Phase 10 coverage for hand-written observation routes."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
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
    OriginType,
    SeasonalAdjustment,
    TemporalStockFlow,
    UnitKind,
    UnitScale,
)
from macro_foundry.models import Geography, Observation, Series


async def _create_country(session: AsyncSession, *, code: str = "USA") -> Geography:
    existing = await session.scalar(select(Geography).where(Geography.code == code))
    if existing is not None:
        return existing

    geography = Geography(
        code=code,
        name="United States",
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
        name=code,
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
async def test_list_observations_filters_by_series_and_period_range(
    client: AsyncClient,
    session: AsyncSession,
    auth_headers: dict[str, str],
) -> None:
    geography = await _create_country(session)
    first_series = await _create_series(session, geography, code="US_CPI")
    second_series = await _create_series(session, geography, code="US_GDP")
    session.add_all(
        [
            Observation(
                series_id=first_series.id,
                period_start=date(2026, 1, 1),
                period_end=date(2026, 1, 31),
                value=Decimal("100.0"),
                vintage_date=date(2026, 2, 15),
            ),
            Observation(
                series_id=first_series.id,
                period_start=date(2026, 2, 1),
                period_end=date(2026, 2, 28),
                value=Decimal("101.0"),
                vintage_date=date(2026, 3, 15),
            ),
            Observation(
                series_id=second_series.id,
                period_start=date(2026, 1, 1),
                period_end=date(2026, 1, 31),
                value=Decimal("999.0"),
                vintage_date=date(2026, 2, 15),
            ),
        ],
    )
    await session.commit()

    response = await client.get(
        "/api/v1/observations/",
        headers=auth_headers,
        params={
            "series_id": str(first_series.id),
            "period_start_from": "2026-02-01",
        },
    )

    assert response.status_code == HTTPStatus.OK
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["series_id"] == str(first_series.id)
    assert payload[0]["period_start"] == "2026-02-01"


@pytest.mark.asyncio
async def test_bulk_observations_accepts_valid_rows_and_reports_invalid_rows(
    client: AsyncClient,
    session: AsyncSession,
    auth_headers: dict[str, str],
) -> None:
    geography = await _create_country(session)
    series = await _create_series(session, geography)

    response = await client.post(
        "/api/v1/observations/bulk",
        headers=auth_headers,
        json=[
            {
                "series_id": str(series.id),
                "period_start": "2026-01-01",
                "period_end": "2026-01-31",
                "value": "100.0",
                "vintage_date": "2026-02-15",
            },
            {
                "series_id": str(series.id),
                "period_start": "2026-02-28",
                "period_end": "2026-02-01",
                "value": "101.0",
                "vintage_date": "2026-03-15",
            },
        ],
    )

    assert response.status_code == HTTPStatus.OK
    payload = response.json()
    assert payload["received"] == 2
    assert payload["accepted"] == 1
    assert payload["inserted"] == 1
    assert payload["updated"] == 0
    assert payload["invalid"] == 1

    stored_rows = (await session.execute(select(Observation))).scalars().all()
    assert len(stored_rows) == 1
    assert stored_rows[0].value == Decimal("100.0")


@pytest.mark.asyncio
async def test_bulk_observations_upserts_existing_vintage_row(
    client: AsyncClient,
    session: AsyncSession,
    auth_headers: dict[str, str],
) -> None:
    geography = await _create_country(session)
    series = await _create_series(session, geography)
    session.add(
        Observation(
            series_id=series.id,
            period_start=date(2026, 1, 1),
            period_end=date(2026, 1, 31),
            value=Decimal("100.0"),
            vintage_date=date(2026, 2, 15),
        ),
    )
    await session.commit()

    response = await client.post(
        "/api/v1/observations/bulk",
        headers=auth_headers,
        json=[
            {
                "series_id": str(series.id),
                "period_start": "2026-01-01",
                "period_end": "2026-01-31",
                "value": "111.5",
                "vintage_date": "2026-02-15",
            }
        ],
    )

    assert response.status_code == HTTPStatus.OK
    payload = response.json()
    assert payload["inserted"] == 0
    assert payload["updated"] == 1

    stored = await session.scalar(
        select(Observation).where(
            Observation.series_id == series.id,
            Observation.period_start == date(2026, 1, 1),
            Observation.vintage_date == date(2026, 2, 15),
        ),
    )
    assert stored is not None
    assert stored.value == Decimal("111.5")
