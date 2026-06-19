"""Smoke coverage for the read-only macrodb MCP tool surface.

The concept/indicator lookup, drill-down, and search tools were retired with the
V7 spine (ADR 0025). What remains is series-grounded: canonical series semantic
search, the selector registry surface, and enum introspection.
"""

from __future__ import annotations

import pytest
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
from macro_foundry.mcp.read_tools import (
    ListEnumValuesArgs,
    MacrodbReadTools,
    SelectorConfigValidationArgs,
    SelectorSchemaArgs,
)
from macro_foundry.models import Geography, Series


@pytest.mark.asyncio
async def test_selector_tools_expose_registry_schema_and_validation(
    session: AsyncSession,
) -> None:
    tools = MacrodbReadTools(session)

    selector_types = await tools.list_selector_types()
    schema = await tools.get_selector_schema(
        SelectorSchemaArgs(selector_type="json_path")
    )
    validation = await tools.validate_selector_config(
        SelectorConfigValidationArgs(
            selector_type="json_path",
            config={"records_path": "observations"},
        ),
    )

    assert selector_types == [
        "censtatd_json",
        "csv_column",
        "estat_value_filter",
        "json_path",
    ]
    assert schema["required"] == [
        "records_path",
        "period_anchor_field",
        "value_field",
        "frequency",
    ]
    assert validation.is_valid is False
    assert "period_anchor_field is required" in validation.errors


@pytest.mark.asyncio
async def test_list_enum_values_reads_named_check_constraint(
    session: AsyncSession,
) -> None:
    tools = MacrodbReadTools(session)

    result = await tools.list_enum_values(
        ListEnumValuesArgs(table="series", column="frequency"),
    )

    assert result.table == "series"
    assert result.column == "frequency"
    assert result.constraint_name == "ck_series_frequency"
    assert result.values == ["D", "W", "M", "Q", "S", "A"]


@pytest.mark.asyncio
async def test_search_series_returns_ranked_hits_for_semantic_query(
    session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    geography = await _get_geography(session, "USA")
    headline = _series("US_CPI_HEADLINE_M_NSA", "USA headline CPI", geography.id)
    core = _series("US_CPI_CORE_M_SA", "USA core CPI", geography.id)
    null_embedding = _series("US_CPI_UNUSED_M_NSA", "USA CPI with null embedding", geography.id)
    headline.embedding = _vector(1.0, 0.0)
    headline.embedding_model = "text-embedding-3-small"
    headline.embedding_input_hash = "headline"
    core.embedding = _vector(0.4, 0.9)
    core.embedding_model = "text-embedding-3-small"
    core.embedding_input_hash = "core"
    session.add_all([headline, core, null_embedding])
    await session.flush()

    tools = MacrodbReadTools(session)
    monkeypatch.setattr(
        "macro_foundry.mcp.read_tools.embed_text",
        lambda query: _embed_query(query),
    )

    result = await tools.search_series("headline inflation monthly United States")

    assert result[0].series.code == "US_CPI_HEADLINE_M_NSA"
    assert result[0].similarity > 0.5
    assert all(0.0 <= hit.similarity <= 1.0 for hit in result)
    assert {hit.series.code for hit in result} == {
        "US_CPI_HEADLINE_M_NSA",
        "US_CPI_CORE_M_SA",
    }


@pytest.mark.asyncio
async def test_search_series_returns_empty_list_for_empty_catalog(
    session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tools = MacrodbReadTools(session)
    monkeypatch.setattr(
        "macro_foundry.mcp.read_tools.embed_text",
        lambda _query: _vector_async(1.0, 0.0),
    )

    assert await tools.search_series("anything") == []


async def _get_geography(session: AsyncSession, code: str) -> Geography:
    geography = await session.scalar(select(Geography).where(Geography.code == code))
    assert geography is not None
    return geography


def _series(code: str, name: str, geography_id: object) -> Series:
    return Series(
        code=code,
        name=name,
        origin_type=OriginType.INGESTED,
        geography_id=geography_id,
        frequency=Frequency.MONTHLY,
        temporal_stock_flow=TemporalStockFlow.INDEX,
        unit_kind=UnitKind.INDEX,
        unit_scale=UnitScale.ONE,
        measure=Measure.LEVEL,
        annualized=False,
        seasonal_adjustment=SeasonalAdjustment.NSA,
        is_active=True,
    )


def _vector(first: float, second: float) -> list[float]:
    return [first, second] + [0.0] * 1534


async def _embed_query(query: str) -> list[float]:
    assert query == "headline inflation monthly United States"
    return _vector(1.0, 0.0)


async def _vector_async(first: float, second: float) -> list[float]:
    return _vector(first, second)
