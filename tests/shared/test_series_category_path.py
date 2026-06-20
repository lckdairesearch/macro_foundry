"""Issue #84: the series API returns the category path (ADR 0025 §1).

The V7 flattened-tag join is gone; a series' topic is now the chain walked up
`category_edges` from its attached concept node. `SeriesReadDetail.category_path`
is that lineage, **most-specific first**: element 0 is the attached `kind=concept`
node, followed by each ancestor up to the domain root. A series with no
`category_id` has an empty path.

These run against the shared session test database, which conftest migrates to
head. The tree fixtures are built in-test (no dependence on seed).
"""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

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
from macro_foundry.models import Category, CategoryEdge, Geography, Series


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


async def _link(session: AsyncSession, parent: Category, child: Category, sort_order: int = 0) -> None:
    session.add(
        CategoryEdge(
            parent_category_id=parent.id,
            child_category_id=child.id,
            sort_order=sort_order,
        ),
    )
    await session.flush()


async def _make_series(session: AsyncSession, code: str, geography: Geography, **overrides: object) -> Series:
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
    series = Series(**base)
    session.add(series)
    await session.flush()
    return series


async def _build_price_tree(session: AsyncSession) -> Category:
    """domain PRICES -> subdomain CONSUMER_PRICES -> concept CPI_ALL_ITEMS."""
    domain = await _make_category(session, "PRICES_T84", CategoryKind.TOPIC)
    subdomain = await _make_category(session, "CONSUMER_PRICES_T84", CategoryKind.TOPIC)
    concept = await _make_category(session, "CPI_ALL_ITEMS_T84", CategoryKind.CONCEPT)
    await _link(session, domain, subdomain)
    await _link(session, subdomain, concept)
    return concept


# ---- the category path ------------------------------------------------------


@pytest.mark.asyncio
async def test_get_series_returns_full_category_path_most_specific_first(
    client, auth_headers, session,
) -> None:
    geography = await _make_geography(session, "US")
    concept = await _build_price_tree(session)
    series = await _make_series(session, "US_CPI_PATH", geography, category_id=concept.id, is_default=True)
    await session.commit()

    resp = await client.get(f"/api/v1/series/{series.id}", headers=auth_headers)
    assert resp.status_code == 200
    path = resp.json()["category_path"]
    assert [node["code"] for node in path] == [
        "CPI_ALL_ITEMS_T84",
        "CONSUMER_PRICES_T84",
        "PRICES_T84",
    ]
    # Element 0 is the attached concept node; the rest is the topic (ancestors).
    assert path[0]["kind"] == "concept"
    assert path[1]["kind"] == "topic"


@pytest.mark.asyncio
async def test_list_series_includes_category_path_per_row(client, auth_headers, session) -> None:
    geography = await _make_geography(session, "US")
    concept = await _build_price_tree(session)
    await _make_series(session, "US_CPI_LIST_PATH", geography, category_id=concept.id, is_default=True)
    await session.commit()

    resp = await client.get(
        "/api/v1/series/",
        params={"category_id": str(concept.id), "geography_id": str(geography.id)},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    hits = {hit["code"]: hit for hit in resp.json()}
    assert [node["code"] for node in hits["US_CPI_LIST_PATH"]["category_path"]] == [
        "CPI_ALL_ITEMS_T84",
        "CONSUMER_PRICES_T84",
        "PRICES_T84",
    ]


@pytest.mark.asyncio
async def test_unclassified_series_has_empty_category_path(client, auth_headers, session) -> None:
    geography = await _make_geography(session, "US")
    series = await _make_series(session, "US_DRAFT_NO_CAT", geography, category_id=None)
    await session.commit()

    resp = await client.get(f"/api/v1/series/{series.id}", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["category_path"] == []


@pytest.mark.asyncio
async def test_concept_leaf_with_no_ancestors_returns_only_itself(client, auth_headers, session) -> None:
    # A concept-leaf attached directly under nothing (root concept) -> path is [self].
    geography = await _make_geography(session, "US")
    concept = await _make_category(session, "EXCHANGE_RATE_T84", CategoryKind.CONCEPT)
    series = await _make_series(session, "US_FX_T84", geography, category_id=concept.id)
    await session.commit()

    resp = await client.get(f"/api/v1/series/{series.id}", headers=auth_headers)
    assert resp.status_code == 200
    assert [node["code"] for node in resp.json()["category_path"]] == ["EXCHANGE_RATE_T84"]
