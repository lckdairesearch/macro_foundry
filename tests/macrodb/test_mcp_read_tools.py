"""Smoke coverage for the read-only macrodb MCP tool surface."""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from macro_foundry.enums import (
    Frequency,
    Measure,
    OriginType,
    ProviderRole,
    ProviderType,
    SeasonalAdjustment,
    TemporalStockFlow,
    UnitKind,
    UnitScale,
)
from macro_foundry.mcp.read_tools import (
    FindSiblingSeriesArgs,
    ListEnumValuesArgs,
    ListProviderSeriesForConceptArgs,
    ListSeriesForConceptArgs,
    LookupConceptArgs,
    LookupFamilyArgs,
    MacrodbReadTools,
    SelectorConfigValidationArgs,
    SelectorSchemaArgs,
)
from macro_foundry.models import (
    Concept,
    Geography,
    Provider,
    ProviderCatalog,
    Series,
    SeriesFamily,
    SeriesFamilyMember,
    SeriesSource,
)


@pytest.mark.asyncio
async def test_lookup_concept_returns_typed_concept_or_none(
    session: AsyncSession,
) -> None:
    session.add(
        Concept(
            code="MCP_CPI",
            name="Consumer price index",
            description="Price index for household consumption goods and services.",
        ),
    )
    await session.flush()
    tools = MacrodbReadTools(session)

    result = await tools.lookup_concept(LookupConceptArgs(code="MCP_CPI"))
    missing = await tools.lookup_concept(LookupConceptArgs(code="NO_SUCH_CONCEPT"))

    assert result is not None
    assert result.code == "MCP_CPI"
    assert result.name == "Consumer price index"
    assert missing is None


@pytest.mark.asyncio
async def test_lookup_family_returns_family_with_members(session: AsyncSession) -> None:
    concept = Concept(code="MCP_FAMILY_CPI", name="Consumer price index")
    geography = await _get_geography(session, "USA")
    session.add(concept)
    await session.flush()
    family = SeriesFamily(
        code="MCP_US_CPI",
        name="US consumer price index",
        concept_id=concept.id,
        geography_id=geography.id,
    )
    series = _series("MCP_US_CPI_HEADLINE", "US CPI headline", geography.id)
    session.add_all([family, series])
    await session.flush()
    session.add(
        SeriesFamilyMember(
            family_id=family.id,
            series_id=series.id,
            variant="Headline NSA",
            is_primary=True,
        ),
    )
    await session.flush()
    tools = MacrodbReadTools(session)

    result = await tools.lookup_family(LookupFamilyArgs(code="MCP_US_CPI"))
    missing = await tools.lookup_family(LookupFamilyArgs(code="NO_SUCH_FAMILY"))

    assert result is not None
    assert result.code == "MCP_US_CPI"
    assert [
        (member.series_id, member.variant, member.is_primary)
        for member in result.members
    ] == [
        (series.id, "Headline NSA", True),
    ]
    assert missing is None


@pytest.mark.asyncio
async def test_find_sibling_series_returns_family_series(session: AsyncSession) -> None:
    concept = Concept(code="MCP_SIBLING_CPI", name="Consumer price index")
    geography = await _get_geography(session, "USA")
    session.add(concept)
    await session.flush()
    family = SeriesFamily(
        code="MCP_US_CPI_SIBLING",
        name="US consumer price index",
        concept_id=concept.id,
        geography_id=geography.id,
    )
    first = _series("MCP_US_CPI_SIBLING_HEADLINE", "US CPI headline", geography.id)
    second = _series("MCP_US_CPI_SIBLING_CORE", "US CPI core", geography.id)
    session.add_all([family, first, second])
    await session.flush()
    session.add_all(
        [
            SeriesFamilyMember(
                family_id=family.id,
                series_id=first.id,
                variant="Headline NSA",
                is_primary=True,
            ),
            SeriesFamilyMember(
                family_id=family.id,
                series_id=second.id,
                variant="Core NSA",
                is_primary=False,
            ),
        ],
    )
    await session.flush()
    tools = MacrodbReadTools(session)

    result = await tools.find_sibling_series(FindSiblingSeriesArgs(family_id=family.id))

    assert [series.code for series in result] == [
        "MCP_US_CPI_SIBLING_HEADLINE",
        "MCP_US_CPI_SIBLING_CORE",
    ]


@pytest.mark.asyncio
async def test_list_series_for_concept_returns_cross_geography_series(
    session: AsyncSession,
) -> None:
    concept = Concept(code="MCP_CONCEPT_GDP", name="Gross domestic product")
    usa = await _get_geography(session, "USA")
    jpn = await _get_geography(session, "JPN")
    session.add(concept)
    await session.flush()
    usa_family = SeriesFamily(
        code="MCP_US_GDP",
        name="US GDP",
        concept_id=concept.id,
        geography_id=usa.id,
    )
    jpn_family = SeriesFamily(
        code="MCP_JP_GDP",
        name="Japan GDP",
        concept_id=concept.id,
        geography_id=jpn.id,
    )
    usa_series = _series("MCP_US_GDP_LEVEL", "US GDP level", usa.id)
    jpn_series = _series("MCP_JP_GDP_LEVEL", "Japan GDP level", jpn.id)
    session.add_all([usa_family, jpn_family, usa_series, jpn_series])
    await session.flush()
    session.add_all(
        [
            SeriesFamilyMember(
                family_id=usa_family.id,
                series_id=usa_series.id,
                is_primary=True,
            ),
            SeriesFamilyMember(
                family_id=jpn_family.id,
                series_id=jpn_series.id,
                is_primary=True,
            ),
        ],
    )
    await session.flush()
    tools = MacrodbReadTools(session)

    result = await tools.list_series_for_concept(
        ListSeriesForConceptArgs(concept_id=concept.id),
    )

    assert [series.code for series in result] == [
        "MCP_JP_GDP_LEVEL",
        "MCP_US_GDP_LEVEL",
    ]


@pytest.mark.asyncio
async def test_list_provider_series_for_concept_returns_provider_cohort(
    session: AsyncSession,
) -> None:
    concept = Concept(code="MCP_PROVIDER_CPI", name="Consumer price index")
    geography = await _get_geography(session, "USA")
    provider = Provider(
        name="MCP Provider",
        type=ProviderType.OFFICIAL,
        is_active=True,
    )
    other_provider = Provider(
        name="MCP Other Provider",
        type=ProviderType.OFFICIAL,
        is_active=True,
    )
    session.add_all([concept, provider, other_provider])
    await session.flush()
    catalog = ProviderCatalog(
        provider_id=provider.id,
        name="Main",
        is_placeholder=True,
    )
    other_catalog = ProviderCatalog(
        provider_id=other_provider.id,
        name="Main",
        is_placeholder=True,
    )
    family = SeriesFamily(
        code="MCP_PROVIDER_US_CPI",
        name="US CPI",
        concept_id=concept.id,
        geography_id=geography.id,
    )
    provider_series = _series("MCP_PROVIDER_US_CPI_SERIES", "US CPI", geography.id)
    other_series = _series(
        "MCP_OTHER_PROVIDER_US_CPI_SERIES", "US CPI other", geography.id
    )
    session.add_all([catalog, other_catalog, family, provider_series, other_series])
    await session.flush()
    session.add_all(
        [
            SeriesFamilyMember(
                family_id=family.id,
                series_id=provider_series.id,
                is_primary=True,
            ),
            SeriesFamilyMember(
                family_id=family.id,
                series_id=other_series.id,
                is_primary=False,
            ),
            SeriesSource(
                series_id=provider_series.id,
                provider_catalog_id=catalog.id,
                external_code="CPI",
                priority=1,
                provider_role=ProviderRole.PRIMARY_SOURCE,
            ),
            SeriesSource(
                series_id=other_series.id,
                provider_catalog_id=other_catalog.id,
                external_code="CPI",
                priority=1,
                provider_role=ProviderRole.PRIMARY_SOURCE,
            ),
        ],
    )
    await session.flush()
    tools = MacrodbReadTools(session)

    result = await tools.list_provider_series_for_concept(
        ListProviderSeriesForConceptArgs(
            provider_id=provider.id,
            concept_id=concept.id,
        ),
    )

    assert [series.code for series in result] == ["MCP_PROVIDER_US_CPI_SERIES"]


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
