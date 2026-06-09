"""Phase 12 coverage for key database constraints."""

from __future__ import annotations

from datetime import date, datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from macro_foundry.enums import (
    CodeStandard,
    FeedMethod,
    ExecutionPolicy,
    Frequency,
    GeographyType,
    IngestionRunStatus,
    IngestionTriggeredBy,
    Measure,
    OriginType,
    ProviderRole,
    ProviderType,
    SeasonalAdjustment,
    TemporalStockFlow,
    UnitKind,
    UnitScale,
)
from macro_foundry.models import (
    Concept,
    DerivedSeries,
    Geography,
    IngestionFeed,
    IngestionFeedMember,
    IngestionRunLog,
    IngestionRunLogMember,
    Observation,
    Provider,
    ProviderCatalog,
    Series,
    SeriesSource,
)


async def _seeded_country(session: AsyncSession, *, code: str = "USA") -> Geography:
    geography = await session.scalar(select(Geography).where(Geography.code == code))
    assert geography is not None
    return geography


async def _create_series(
    session: AsyncSession,
    *,
    code: str,
    geography_id: object | None = None,
    origin_type: OriginType = OriginType.INGESTED,
    unit_kind: UnitKind = UnitKind.INDEX,
    currency_code: str | None = None,
    measure: Measure = Measure.LEVEL,
) -> Series:
    if geography_id is None:
        geography_id = (await _seeded_country(session)).id

    series = Series(
        code=code,
        name=f"{code} name",
        origin_type=origin_type,
        geography_id=geography_id,
        frequency=Frequency.MONTHLY,
        temporal_stock_flow=TemporalStockFlow.INDEX,
        unit_kind=unit_kind,
        unit_scale=UnitScale.ONE,
        currency_code=currency_code,
        measure=measure,
        annualized=False,
        seasonal_adjustment=SeasonalAdjustment.NSA,
        is_active=True,
    )
    session.add(series)
    await session.commit()
    await session.refresh(series)
    return series


async def _create_provider_catalog(
    session: AsyncSession,
    *,
    provider_name: str = "Macro Foundry Test Provider",
    catalog_name: str = "Macro Foundry Test Catalog",
) -> ProviderCatalog:
    provider = Provider(
        name=provider_name,
        type=ProviderType.OTHER,
        is_active=True,
    )
    session.add(provider)
    await session.commit()
    await session.refresh(provider)

    catalog = ProviderCatalog(
        provider_id=provider.id,
        name=catalog_name,
        is_placeholder=False,
    )
    session.add(catalog)
    await session.commit()
    await session.refresh(catalog)
    return catalog


@pytest.mark.asyncio
async def test_concept_code_is_unique(
    session: AsyncSession,
) -> None:
    session.add(Concept(code="MF_DUPLICATE", name="First concept"))
    await session.commit()

    session.add(Concept(code="MF_DUPLICATE", name="Second concept"))
    with pytest.raises(IntegrityError):
        await session.commit()
    await session.rollback()


@pytest.mark.asyncio
async def test_geography_subnational_types_require_parent(
    session: AsyncSession,
) -> None:
    session.add(
        Geography(
            code="US-ZZ",
            name="Imaginary State",
            type=GeographyType.SUBNATIONAL,
            code_standard=CodeStandard.ISO_3166_2,
        ),
    )

    with pytest.raises(IntegrityError):
        await session.commit()
    await session.rollback()


@pytest.mark.asyncio
async def test_series_growth_measure_requires_horizon(
    session: AsyncSession,
) -> None:
    geography = await _seeded_country(session)
    session.add(
        Series(
            code="MF_GROWTH_BAD",
            name="Bad growth series",
            origin_type=OriginType.INGESTED,
            geography_id=geography.id,
            frequency=Frequency.MONTHLY,
            temporal_stock_flow=TemporalStockFlow.INDEX,
            unit_kind=UnitKind.PERCENT,
            unit_scale=UnitScale.ONE,
            measure=Measure.GROWTH,
            annualized=False,
            seasonal_adjustment=SeasonalAdjustment.NSA,
            is_active=True,
        ),
    )

    with pytest.raises(IntegrityError):
        await session.commit()
    await session.rollback()


@pytest.mark.asyncio
async def test_series_currency_unit_requires_currency_code(
    session: AsyncSession,
) -> None:
    geography = await _seeded_country(session)
    session.add(
        Series(
            code="MF_CURRENCY_BAD",
            name="Bad currency series",
            origin_type=OriginType.INGESTED,
            geography_id=geography.id,
            frequency=Frequency.MONTHLY,
            temporal_stock_flow=TemporalStockFlow.FLOW,
            unit_kind=UnitKind.CURRENCY,
            unit_scale=UnitScale.BILLION,
            measure=Measure.LEVEL,
            annualized=False,
            seasonal_adjustment=SeasonalAdjustment.NSA,
            is_active=True,
        ),
    )

    with pytest.raises(IntegrityError):
        await session.commit()
    await session.rollback()


@pytest.mark.asyncio
async def test_observation_period_end_must_not_precede_period_start(
    session: AsyncSession,
) -> None:
    series = await _create_series(session, code="MF_OBS_BOUNDS")

    session.add(
        Observation(
            series_id=series.id,
            period_start=date(2026, 1, 31),
            period_end=date(2026, 1, 1),
            vintage_date=date(2026, 2, 15),
        ),
    )

    with pytest.raises(IntegrityError):
        await session.commit()
    await session.rollback()


@pytest.mark.asyncio
async def test_series_requires_existing_geography(
    session: AsyncSession,
) -> None:
    session.add(
        Series(
            code="MF_BAD_GEOGRAPHY",
            name="Invalid geography FK",
            origin_type=OriginType.INGESTED,
            geography_id=uuid4(),
            frequency=Frequency.MONTHLY,
            temporal_stock_flow=TemporalStockFlow.INDEX,
            unit_kind=UnitKind.INDEX,
            unit_scale=UnitScale.ONE,
            measure=Measure.LEVEL,
            annualized=False,
            seasonal_adjustment=SeasonalAdjustment.NSA,
            is_active=True,
        ),
    )

    with pytest.raises(IntegrityError):
        await session.commit()
    await session.rollback()


@pytest.mark.asyncio
async def test_provider_catalog_requires_existing_provider(
    session: AsyncSession,
) -> None:
    session.add(
        ProviderCatalog(
            provider_id=uuid4(),
            name="Invalid provider catalog",
            is_placeholder=False,
        ),
    )

    with pytest.raises(IntegrityError):
        await session.commit()
    await session.rollback()


@pytest.mark.asyncio
async def test_series_source_external_code_is_not_unique_within_catalog(
    session: AsyncSession,
) -> None:
    series_one = await _create_series(session, code="MF_SOURCE_SERIES_ONE")
    series_two = await _create_series(session, code="MF_SOURCE_SERIES_TWO")
    catalog = await _create_provider_catalog(session)

    session.add(
        SeriesSource(
            series_id=series_one.id,
            provider_catalog_id=catalog.id,
            external_code="MF-EXT",
            priority=1,
            provider_role=ProviderRole.PRIMARY_SOURCE,
        ),
    )
    await session.commit()

    session.add(
        SeriesSource(
            series_id=series_two.id,
            provider_catalog_id=catalog.id,
            external_code="MF-EXT",
            priority=2,
            provider_role=ProviderRole.REDISTRIBUTOR,
        ),
    )
    await session.commit()

    rows = (
        await session.execute(
            select(SeriesSource).where(
                SeriesSource.provider_catalog_id == catalog.id,
                SeriesSource.external_code == "MF-EXT",
            ),
        )
    ).scalars().all()
    assert len(rows) == 2


@pytest.mark.asyncio
async def test_series_source_allows_nullable_external_code_and_ref_url(
    session: AsyncSession,
) -> None:
    series = await _create_series(session, code="MF_SOURCE_NO_CODE")
    catalog = await _create_provider_catalog(
        session,
        provider_name="Macro Foundry Nullable Source Provider",
        catalog_name="Macro Foundry Nullable Source Catalog",
    )

    source = SeriesSource(
        series_id=series.id,
        provider_catalog_id=catalog.id,
        external_name="Source without a clean provider code",
        ref_url="https://example.test/source",
        priority=1,
        provider_role=ProviderRole.PRIMARY_SOURCE,
    )
    session.add(source)
    await session.commit()
    await session.refresh(source)

    assert source.external_code is None
    assert source.ref_url == "https://example.test/source"


@pytest.mark.asyncio
async def test_ingestion_feed_member_allows_only_one_member_per_series_source(
    session: AsyncSession,
) -> None:
    series = await _create_series(session, code="MF_FEED_MEMBER_UNIQUE")
    catalog = await _create_provider_catalog(
        session,
        provider_name="Macro Foundry Feed Member Provider",
        catalog_name="Macro Foundry Feed Member Catalog",
    )
    source = SeriesSource(
        series_id=series.id,
        provider_catalog_id=catalog.id,
        priority=1,
        provider_role=ProviderRole.PRIMARY_SOURCE,
    )
    session.add(source)
    feed_one = IngestionFeed(feed_method=FeedMethod.API, endpoint_url="/one", is_active=True)
    feed_two = IngestionFeed(feed_method=FeedMethod.API, endpoint_url="/two", is_active=True)
    session.add_all([feed_one, feed_two])
    await session.commit()

    session.add(
        IngestionFeedMember(
            ingestion_feed_id=feed_one.id,
            series_source_id=source.id,
            selector_type="json_path",
            selector_config={"path": "$.one"},
            is_active=True,
        ),
    )
    await session.commit()

    session.add(
        IngestionFeedMember(
            ingestion_feed_id=feed_two.id,
            series_source_id=source.id,
            selector_type="json_path",
            selector_config={"path": "$.two"},
            is_active=True,
        ),
    )

    with pytest.raises(IntegrityError):
        await session.commit()
    await session.rollback()


@pytest.mark.asyncio
async def test_ingestion_run_log_member_allows_only_one_outcome_per_member_attempt(
    session: AsyncSession,
) -> None:
    series = await _create_series(session, code="MF_RUN_LOG_MEMBER_UNIQUE")
    catalog = await _create_provider_catalog(
        session,
        provider_name="Macro Foundry Run Member Provider",
        catalog_name="Macro Foundry Run Member Catalog",
    )
    source = SeriesSource(
        series_id=series.id,
        provider_catalog_id=catalog.id,
        priority=1,
        provider_role=ProviderRole.PRIMARY_SOURCE,
    )
    feed = IngestionFeed(feed_method=FeedMethod.API, endpoint_url="/shared", is_active=True)
    session.add_all([source, feed])
    await session.commit()

    member = IngestionFeedMember(
        ingestion_feed_id=feed.id,
        series_source_id=source.id,
        selector_type="json_path",
        selector_config={"path": "$.value"},
        is_active=True,
    )
    run_log = IngestionRunLog(
        ingestion_feed_id=feed.id,
        started_at=datetime(2026, 6, 9, tzinfo=timezone.utc),
        status=IngestionRunStatus.PARTIAL,
        triggered_by=IngestionTriggeredBy.MANUAL,
    )
    session.add_all([member, run_log])
    await session.commit()

    session.add(
        IngestionRunLogMember(
            ingestion_run_log_id=run_log.id,
            ingestion_feed_member_id=member.id,
            status=IngestionRunStatus.SUCCESS,
            rows_inserted=1,
        ),
    )
    await session.commit()

    session.add(
        IngestionRunLogMember(
            ingestion_run_log_id=run_log.id,
            ingestion_feed_member_id=member.id,
            status=IngestionRunStatus.FAILED,
            error_message="Duplicate outcome for the same attempt.",
        ),
    )

    with pytest.raises(IntegrityError):
        await session.commit()
    await session.rollback()


@pytest.mark.asyncio
async def test_observation_vintage_key_is_unique(
    session: AsyncSession,
) -> None:
    series = await _create_series(session, code="MF_OBS_UNIQUE")

    session.add(
        Observation(
            series_id=series.id,
            period_start=date(2026, 1, 1),
            period_end=date(2026, 1, 31),
            vintage_date=date(2026, 2, 15),
        ),
    )
    await session.commit()

    session.add(
        Observation(
            series_id=series.id,
            period_start=date(2026, 1, 1),
            period_end=date(2026, 1, 31),
            vintage_date=date(2026, 2, 15),
        ),
    )

    with pytest.raises(IntegrityError):
        await session.commit()
    await session.rollback()


@pytest.mark.asyncio
async def test_derived_series_allows_only_one_row_per_series(
    session: AsyncSession,
) -> None:
    series = await _create_series(
        session,
        code="MF_DERIVED_ONLY",
        origin_type=OriginType.DERIVED,
    )

    session.add(
        DerivedSeries(
            series_id=series.id,
            description="First derived definition",
            execution_policy=ExecutionPolicy.MANUAL,
            is_deterministic=True,
            requires_vintage_awareness=False,
        ),
    )
    await session.commit()

    session.add(
        DerivedSeries(
            series_id=series.id,
            description="Duplicate derived definition",
            execution_policy=ExecutionPolicy.MANUAL,
            is_deterministic=True,
            requires_vintage_awareness=False,
        ),
    )

    with pytest.raises(IntegrityError):
        await session.commit()
    await session.rollback()
