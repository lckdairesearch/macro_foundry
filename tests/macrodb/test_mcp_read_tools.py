"""Smoke coverage for the read-only macrodb MCP tool surface."""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from macro_foundry.bootstrap import EnvTarget, run_fred_us_macro_bootstrap
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
from macro_foundry.ingestion.providers import FredObservation, FredSeriesMetadata
from macro_foundry.models import (
    Concept,
    Geography,
    Provider,
    ProviderCatalog,
    Series,
    Indicator,
    IndicatorVariant,
    SeriesSource,
)
from macro_foundry.services.embeddings import EMBEDDING_DIMENSIONS


@pytest.fixture(autouse=True)
def mock_registration_embed_text(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_embed_text(text: str) -> list[float]:
        fill = float((sum(ord(ch) for ch in text) % 7) + 1)
        return [fill] * EMBEDDING_DIMENSIONS

    monkeypatch.setattr(
        "macro_foundry.services.registration.embed_text",
        fake_embed_text,
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
    family = Indicator(
        code="MCP_US_CPI",
        name="US consumer price index",
        concept_id=concept.id,
        geography_id=geography.id,
    )
    series = _series("MCP_US_CPI_HEADLINE", "US CPI headline", geography.id)
    session.add_all([family, series])
    await session.flush()
    session.add(
        IndicatorVariant(
            indicator_id=family.id,
            series_id=series.id,
            label="Headline NSA",
            is_default=True,
        ),
    )
    await session.flush()
    tools = MacrodbReadTools(session)

    result = await tools.lookup_family(LookupFamilyArgs(code="MCP_US_CPI"))
    missing = await tools.lookup_family(LookupFamilyArgs(code="NO_SUCH_FAMILY"))

    assert result is not None
    assert result.code == "MCP_US_CPI"
    assert [
        (member.series_id, member.label, member.is_default)
        for member in result.variants
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
    family = Indicator(
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
            IndicatorVariant(
                indicator_id=family.id,
                series_id=first.id,
                label="Headline NSA",
                is_default=True,
            ),
            IndicatorVariant(
                indicator_id=family.id,
                series_id=second.id,
                label="Core NSA",
                is_default=False,
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
    usa_family = Indicator(
        code="MCP_US_GDP",
        name="US GDP",
        concept_id=concept.id,
        geography_id=usa.id,
    )
    jpn_family = Indicator(
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
            IndicatorVariant(
                indicator_id=usa_family.id,
                series_id=usa_series.id,
                is_default=True,
            ),
            IndicatorVariant(
                indicator_id=jpn_family.id,
                series_id=jpn_series.id,
                is_default=True,
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
    family = Indicator(
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
            IndicatorVariant(
                indicator_id=family.id,
                series_id=provider_series.id,
                is_default=True,
            ),
            IndicatorVariant(
                indicator_id=family.id,
                series_id=other_series.id,
                is_default=False,
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


@pytest.mark.asyncio
async def test_search_series_returns_ranked_hits_for_semantic_query(
    session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    concept = Concept(code="CPI", name="Consumer Price Index")
    geography = await _get_geography(session, "USA")
    family = Indicator(
        code="US_CPI",
        name="United States Consumer Price Index",
        concept=concept,
        geography=geography,
    )
    headline = _series(
        "US_CPI_HEADLINE_M_NSA",
        "USA headline CPI",
        geography.id,
    )
    core = _series(
        "US_CPI_CORE_M_SA",
        "USA core CPI",
        geography.id,
    )
    null_embedding = _series(
        "US_CPI_UNUSED_M_NSA",
        "USA CPI with null embedding",
        geography.id,
    )
    headline.embedding = _vector(1.0, 0.0)
    headline.embedding_model = "text-embedding-3-small"
    headline.embedding_input_hash = "headline"
    core.embedding = _vector(0.4, 0.9)
    core.embedding_model = "text-embedding-3-small"
    core.embedding_input_hash = "core"
    session.add_all([concept, family, headline, core, null_embedding])
    await session.flush()
    session.add_all(
        [
            IndicatorVariant(
                indicator=family,
                series=headline,
                is_default=True,
            ),
            IndicatorVariant(
                indicator=family,
                series=core,
                is_default=False,
            ),
            IndicatorVariant(
                indicator=family,
                series=null_embedding,
                is_default=False,
            ),
        ],
    )
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
async def test_search_concepts_returns_ranked_hits_for_semantic_query(
    session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cpi = Concept(
        code="CPI",
        name="Consumer Price Index",
        embedding=_vector(1.0, 0.0),
        embedding_model="text-embedding-3-small",
        embedding_input_hash="cpi",
    )
    gdp = Concept(
        code="GDP",
        name="Gross Domestic Product",
        embedding=_vector(0.0, 1.0),
        embedding_model="text-embedding-3-small",
        embedding_input_hash="gdp",
    )
    missing_embedding = Concept(
        code="PPI",
        name="Producer Price Index",
    )
    session.add_all([cpi, gdp, missing_embedding])
    await session.flush()
    tools = MacrodbReadTools(session)
    monkeypatch.setattr(
        "macro_foundry.mcp.read_tools.embed_text",
        lambda query: _embed_cpi_query(query),
    )

    result = await tools.search_concepts("consumer inflation concept")

    assert result[0].concept.code == "CPI"
    assert result[0].similarity > 0.5
    assert {hit.concept.code for hit in result} == {"CPI", "GDP"}


@pytest.mark.asyncio
async def test_search_series_families_returns_ranked_hits_with_members(
    session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    concept = Concept(code="CPI", name="Consumer Price Index")
    geography = await _get_geography(session, "USA")
    family = Indicator(
        code="US_CPI",
        name="United States Consumer Price Index",
        concept=concept,
        geography=geography,
        embedding=_vector(1.0, 0.0),
        embedding_model="text-embedding-3-small",
        embedding_input_hash="us-cpi",
    )
    other_family = Indicator(
        code="US_GDP",
        name="United States Gross Domestic Product",
        concept=concept,
        geography=geography,
        embedding=_vector(0.0, 1.0),
        embedding_model="text-embedding-3-small",
        embedding_input_hash="us-gdp",
    )
    headline = _series("US_CPI_HEADLINE_M_NSA", "USA headline CPI", geography.id)
    session.add_all([concept, family, other_family, headline])
    await session.flush()
    session.add(
        IndicatorVariant(
            indicator=family,
            series=headline,
            label="Headline",
            is_default=True,
        ),
    )
    await session.flush()
    tools = MacrodbReadTools(session)
    monkeypatch.setattr(
        "macro_foundry.mcp.read_tools.embed_text",
        lambda query: _embed_family_query(query),
    )

    result = await tools.search_series_families("us inflation family")

    assert result[0].indicator.code == "US_CPI"
    assert result[0].similarity > 0.5
    assert [
        (member.series_id, member.label, member.is_default)
        for member in result[0].indicator.variants
    ] == [
        (headline.id, "Headline", True),
    ]


@pytest.mark.asyncio
async def test_search_series_ranks_fred_headline_cpi_top_hit(
    test_session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await run_fred_us_macro_bootstrap(
        target=EnvTarget.TEST,
        session_factory=test_session_factory,
        client=_build_fake_fred_client(),
        run_date=date(2026, 6, 9),
    )

    async with test_session_factory() as session:
        await _assign_series_embedding(session, "US_CPI_HEADLINE_M_NSA", _vector(1.0, 0.0))
        await _assign_series_embedding(session, "US_CPI_CORE_M_SA", _vector(0.8, 0.2))
        await _assign_series_embedding(session, "US_GDP_REAL_Q_SAAR", _vector(0.0, 1.0))
        await _assign_series_embedding(session, "US_GDP_NOMINAL_Q_SAAR", _vector(0.2, 0.8))
        tools = MacrodbReadTools(session)
        monkeypatch.setattr(
            "macro_foundry.mcp.read_tools.embed_text",
            lambda query: _embed_query(query),
        )

        result = await tools.search_series("headline inflation monthly United States")

        assert result[0].series.code == "US_CPI_HEADLINE_M_NSA"
        assert result[0].similarity > 0.5


@pytest.mark.asyncio
async def test_search_series_ranks_fred_real_gdp_top_hit(
    test_session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await run_fred_us_macro_bootstrap(
        target=EnvTarget.TEST,
        session_factory=test_session_factory,
        client=_build_fake_fred_client(),
        run_date=date(2026, 6, 9),
    )

    async with test_session_factory() as session:
        await _assign_series_embedding(session, "US_CPI_HEADLINE_M_NSA", _vector(1.0, 0.0))
        await _assign_series_embedding(session, "US_CPI_CORE_M_SA", _vector(0.7, 0.2))
        await _assign_series_embedding(session, "US_GDP_REAL_Q_SAAR", _vector(0.0, 1.0))
        await _assign_series_embedding(session, "US_GDP_NOMINAL_Q_SAAR", _vector(0.2, 0.8))
        tools = MacrodbReadTools(session)
        monkeypatch.setattr(
            "macro_foundry.mcp.read_tools.embed_text",
            lambda query: _embed_gdp_query(query),
        )

        result = await tools.search_series("real GDP growth quarterly US")

        assert result[0].series.code == "US_GDP_REAL_Q_SAAR"


@pytest.mark.asyncio
async def test_semantic_search_tools_return_empty_lists_for_empty_catalog(
    session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tools = MacrodbReadTools(session)
    monkeypatch.setattr(
        "macro_foundry.mcp.read_tools.embed_text",
        lambda _query: _vector_async(1.0, 0.0),
    )

    concept_hits = await tools.search_concepts("anything")
    family_hits = await tools.search_series_families("anything")
    series_hits = await tools.search_series("anything")

    assert concept_hits == []
    assert family_hits == []
    assert series_hits == []


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


async def _assign_series_embedding(
    session: AsyncSession,
    code: str,
    embedding: list[float],
) -> None:
    series = await session.scalar(select(Series).where(Series.code == code))
    assert series is not None
    series.embedding = embedding
    series.embedding_model = "text-embedding-3-small"
    series.embedding_input_hash = code.lower()
    await session.flush()


async def _embed_query(query: str) -> list[float]:
    assert query == "headline inflation monthly United States"
    return _vector(1.0, 0.0)


async def _embed_cpi_query(query: str) -> list[float]:
    assert query == "consumer inflation concept"
    return _vector(1.0, 0.0)


async def _embed_family_query(query: str) -> list[float]:
    assert query == "us inflation family"
    return _vector(1.0, 0.0)


async def _embed_gdp_query(query: str) -> list[float]:
    assert query == "real GDP growth quarterly US"
    return _vector(0.0, 1.0)


async def _vector_async(first: float, second: float) -> list[float]:
    return _vector(first, second)


class _FakeFredClient:
    def __init__(
        self,
        *,
        metadata_by_series_id: dict[str, FredSeriesMetadata],
        observations_by_series_id: dict[str, list[FredObservation]],
    ) -> None:
        self.metadata_by_series_id = metadata_by_series_id
        self.observations_by_series_id = observations_by_series_id
        self.observation_starts: dict[str, list[date | None]] = defaultdict(list)
        self.metadata_endpoints: dict[str, list[str]] = defaultdict(list)
        self.observation_endpoints: dict[str, list[str]] = defaultdict(list)

    async def fetch_series_metadata(
        self,
        series_id: str,
        *,
        endpoint_path: str = "/series",
    ) -> FredSeriesMetadata:
        self.metadata_endpoints[series_id].append(endpoint_path)
        return self.metadata_by_series_id[series_id]

    async def fetch_series_observations(
        self,
        series_id: str,
        *,
        observation_start: date | None = None,
        endpoint_path: str = "/series/observations",
    ) -> list[FredObservation]:
        self.observation_starts[series_id].append(observation_start)
        self.observation_endpoints[series_id].append(endpoint_path)
        rows = self.observations_by_series_id[series_id]
        if observation_start is None:
            return list(rows)
        return [
            row
            for row in rows
            if row.period_anchor >= observation_start
        ]


def _build_fake_fred_client() -> _FakeFredClient:
    return _FakeFredClient(
        metadata_by_series_id={
            "GDP": FredSeriesMetadata(
                series_id="GDP",
                title="Gross Domestic Product",
                frequency=Frequency.QUARTERLY,
                observation_start=date(2025, 1, 1),
                observation_end=date(2026, 4, 1),
            ),
            "GDPC1": FredSeriesMetadata(
                series_id="GDPC1",
                title="Real Gross Domestic Product",
                frequency=Frequency.QUARTERLY,
                observation_start=date(2025, 1, 1),
                observation_end=date(2026, 4, 1),
            ),
            "CPIAUCNS": FredSeriesMetadata(
                series_id="CPIAUCNS",
                title="Consumer Price Index for All Urban Consumers: All Items in U.S. City Average",
                frequency=Frequency.MONTHLY,
                observation_start=date(2025, 1, 1),
                observation_end=date(2026, 2, 1),
            ),
            "CPILFESL": FredSeriesMetadata(
                series_id="CPILFESL",
                title="Consumer Price Index for All Urban Consumers: All Items Less Food and Energy in U.S. City Average",
                frequency=Frequency.MONTHLY,
                observation_start=date(2025, 1, 1),
                observation_end=date(2026, 2, 1),
            ),
        },
        observations_by_series_id={
            "GDP": [
                FredObservation(period_anchor=date(2025, 1, 1), value=Decimal("30000")),
                FredObservation(period_anchor=date(2025, 4, 1), value=Decimal("30100")),
                FredObservation(period_anchor=date(2026, 1, 1), value=Decimal("31500")),
                FredObservation(period_anchor=date(2026, 4, 1), value=Decimal("31650")),
            ],
            "GDPC1": [
                FredObservation(period_anchor=date(2025, 1, 1), value=Decimal("22000")),
                FredObservation(period_anchor=date(2025, 4, 1), value=Decimal("22100")),
                FredObservation(period_anchor=date(2026, 1, 1), value=Decimal("22550")),
                FredObservation(period_anchor=date(2026, 4, 1), value=Decimal("22625")),
            ],
            "CPIAUCNS": [
                FredObservation(period_anchor=date(2025, 1, 1), value=Decimal("100")),
                FredObservation(period_anchor=date(2025, 2, 1), value=Decimal("101")),
                FredObservation(period_anchor=date(2025, 3, 1), value=Decimal("102")),
                FredObservation(period_anchor=date(2026, 1, 1), value=Decimal("103")),
                FredObservation(period_anchor=date(2026, 2, 1), value=Decimal("104")),
            ],
            "CPILFESL": [
                FredObservation(period_anchor=date(2025, 1, 1), value=Decimal("110")),
                FredObservation(period_anchor=date(2025, 2, 1), value=Decimal("111")),
                FredObservation(period_anchor=date(2025, 3, 1), value=Decimal("112")),
                FredObservation(period_anchor=date(2026, 1, 1), value=Decimal("113")),
                FredObservation(period_anchor=date(2026, 2, 1), value=Decimal("114")),
            ],
        },
    )
