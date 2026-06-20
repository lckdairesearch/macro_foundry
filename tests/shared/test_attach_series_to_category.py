"""Issue #80: attach a series to its most-specific concept node (ADR 0025 §3).

Migration 0019 adds `series.category_id` (nullable FK -> categories.id, ON DELETE
RESTRICT) and `series.is_default` (NOT NULL, default false). The "concept-only,
never a topic" rule is an app-layer guardrail (service + API), not a DB
constraint. The derived "indicator" grain is the query `(category_id,
geography_id)`; the default reading adds `AND is_default`.

These run against the shared session test database, which conftest migrates to
head. Category and geography fixtures are built in-test (no dependence on seed).
"""

from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from macro_foundry.config import settings
from macro_foundry.enums import (
    CategoryKind,
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
from macro_foundry.models import Category, Geography, Series
from macro_foundry.services.registration import (
    CategoryAttachmentError,
    ensure_category_is_concept,
)


# ---- in-test fixtures -------------------------------------------------------


async def _make_geography(session: AsyncSession, code: str) -> Geography:
    geography = Geography(
        code=code,
        name=f"Geo {code}",
        type=GeographyType.COUNTRY,
        code_standard=CodeStandard.ISO_3166_1,
    )
    session.add(geography)
    await session.flush()
    return geography


async def _make_category(session: AsyncSession, code: str, kind: CategoryKind) -> Category:
    category = Category(code=code, name=f"Cat {code}", kind=kind)
    session.add(category)
    await session.flush()
    return category


def _series_kwargs(code: str, geography: Geography, **overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "code": code,
        "name": f"Series {code}",
        "origin_type": OriginType.INGESTED,
        "geography_id": geography.id,
        "frequency": Frequency.MONTHLY,
        "temporal_stock_flow": TemporalStockFlow.INDEX,
        "unit_kind": UnitKind.INDEX,
        "unit_scale": UnitScale.ONE,
        "measure": Measure.LEVEL,
        "annualized": False,
        "seasonal_adjustment": SeasonalAdjustment.NSA,
        "is_active": True,
        "is_default": False,
    }
    base.update(overrides)
    return base


async def _make_series(session: AsyncSession, code: str, geography: Geography, **overrides: object) -> Series:
    series = Series(**_series_kwargs(code, geography, **overrides))
    session.add(series)
    await session.flush()
    return series


# ---- migration: columns + round-trip ----------------------------------------


async def _assert_series_columns_present() -> None:
    engine = create_async_engine(settings.db.owner_url, pool_pre_ping=True)
    try:
        async with engine.connect() as conn:
            rows = await conn.exec_driver_sql(
                """
                SELECT column_name, is_nullable, data_type
                FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = 'series'
                  AND column_name IN ('category_id', 'is_default')
                """,
            )
            columns = {row[0]: (row[1], row[2]) for row in rows}
        assert columns["category_id"][0] == "YES"
        assert columns["is_default"][0] == "NO"
    finally:
        await engine.dispose()


async def _assert_category_fk_restricts_delete() -> None:
    engine = create_async_engine(settings.db.owner_url, pool_pre_ping=True)
    try:
        async with engine.connect() as conn:
            rows = await conn.exec_driver_sql(
                """
                SELECT rc.delete_rule
                FROM information_schema.referential_constraints rc
                JOIN information_schema.table_constraints tc
                  ON tc.constraint_name = rc.constraint_name
                WHERE tc.table_name = 'series'
                  AND rc.constraint_name = 'fk_series_category_id_categories'
                """,
            )
            delete_rules = {row[0] for row in rows}
        assert delete_rules == {"RESTRICT"}
    finally:
        await engine.dispose()


def test_series_gains_category_id_and_is_default_columns() -> None:
    asyncio.run(_assert_series_columns_present())


def test_series_category_fk_is_on_delete_restrict() -> None:
    asyncio.run(_assert_category_fk_restricts_delete())


# ---- app-layer guardrail: concept-only attachment ---------------------------


@pytest.mark.asyncio
async def test_null_category_is_accepted(session: AsyncSession) -> None:
    # No raise; null is a draft/unclassified series.
    await ensure_category_is_concept(session, None)


@pytest.mark.asyncio
async def test_concept_category_is_accepted(session: AsyncSession) -> None:
    concept = await _make_category(session, "TEST_CPI_CONCEPT", CategoryKind.CONCEPT)
    await ensure_category_is_concept(session, concept.id)  # no raise


@pytest.mark.asyncio
async def test_topic_category_is_rejected_with_clear_error(session: AsyncSession) -> None:
    topic = await _make_category(session, "TEST_PRICES_TOPIC", CategoryKind.TOPIC)
    with pytest.raises(CategoryAttachmentError) as exc_info:
        await ensure_category_is_concept(session, topic.id)
    message = str(exc_info.value)
    assert "kind=concept" in message
    assert "topic" in message
    assert "TEST_PRICES_TOPIC" in message


@pytest.mark.asyncio
async def test_missing_category_is_rejected(session: AsyncSession) -> None:
    with pytest.raises(CategoryAttachmentError):
        await ensure_category_is_concept(session, uuid4())


# ---- attachment + eager loading (no MissingGreenlet) ------------------------


@pytest.mark.asyncio
async def test_series_attaches_to_concept_and_relationship_is_eager(session: AsyncSession) -> None:
    geography = await _make_geography(session, "US")
    concept = await _make_category(session, "CPI_ALL_ITEMS_US", CategoryKind.CONCEPT)
    series = await _make_series(session, "US_CPI", geography, category_id=concept.id, is_default=True)

    # Re-fetch through a fresh select; accessing .category must not lazy-load.
    refetched = await session.get(Series, series.id)
    assert refetched is not None
    assert refetched.category is not None
    assert refetched.category.code == "CPI_ALL_ITEMS_US"
    assert refetched.is_default is True


@pytest.mark.asyncio
async def test_category_delete_is_restricted_while_series_attached(session: AsyncSession) -> None:
    geography = await _make_geography(session, "GB")
    concept = await _make_category(session, "GDP_REAL_GB", CategoryKind.CONCEPT)
    await _make_series(session, "GB_GDP", geography, category_id=concept.id)

    with pytest.raises(IntegrityError):
        await session.execute(text("DELETE FROM categories WHERE id = :cid"), {"cid": concept.id})
        await session.flush()


# ---- derived reads: the (category_id, geography_id) "indicator" query --------


@pytest.mark.asyncio
async def test_indicator_query_and_default_filter(client, auth_headers, session) -> None:
    us = await _make_geography(session, "US")
    gb = await _make_geography(session, "GB")
    concept = await _make_category(session, "TEST_CPI_CONCEPT", CategoryKind.CONCEPT)
    other_concept = await _make_category(session, "TEST_GDP_CONCEPT", CategoryKind.CONCEPT)

    await _make_series(session, "US_CPI_HEADLINE", us, category_id=concept.id, is_default=True)
    await _make_series(session, "US_CPI_CORE", us, category_id=concept.id, is_default=False)
    await _make_series(session, "GB_CPI_HEADLINE", gb, category_id=concept.id, is_default=True)
    await _make_series(session, "US_GDP", us, category_id=other_concept.id, is_default=True)
    await session.commit()

    # Indicator query: (category_id, geography_id) -> the US CPI readings only.
    resp = await client.get(
        "/api/v1/series/",
        params={"category_id": str(concept.id), "geography_id": str(us.id)},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    codes = {hit["code"] for hit in resp.json()}
    assert codes == {"US_CPI_HEADLINE", "US_CPI_CORE"}

    # Default reading within (category_id, geography_id).
    resp_default = await client.get(
        "/api/v1/series/",
        params={"category_id": str(concept.id), "geography_id": str(us.id), "is_default": "true"},
        headers=auth_headers,
    )
    assert resp_default.status_code == 200
    default_codes = {hit["code"] for hit in resp_default.json()}
    assert default_codes == {"US_CPI_HEADLINE"}

    # Cross-geography concept read: all geographies under the concept node.
    resp_cross = await client.get(
        "/api/v1/series/",
        params={"category_id": str(concept.id)},
        headers=auth_headers,
    )
    assert resp_cross.status_code == 200
    cross_codes = {hit["code"] for hit in resp_cross.json()}
    assert cross_codes == {"US_CPI_HEADLINE", "US_CPI_CORE", "GB_CPI_HEADLINE"}


@pytest.mark.asyncio
async def test_create_series_rejects_topic_category(client, auth_headers, session) -> None:
    geography = await _make_geography(session, "US")
    topic = await _make_category(session, "TEST_PRICES_TOPIC", CategoryKind.TOPIC)
    await session.commit()

    payload = _series_kwargs("US_BAD", geography, category_id=str(topic.id))
    payload["geography_id"] = str(geography.id)
    # Serialize enums to their values for JSON transport.
    json_payload = {
        key: (value.value if hasattr(value, "value") else value)
        for key, value in payload.items()
    }
    resp = await client.post("/api/v1/series/", json=json_payload, headers=auth_headers)
    assert resp.status_code == 422
    assert "kind=concept" in str(resp.json()["detail"])
