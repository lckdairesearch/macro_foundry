"""Request-centric debug bootstrap for local inspection."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from macro_foundry.db import (
    EnvTarget,
    app_url_for_target,
    create_async_engine_for_url,
    create_session_factory,
)
from macro_foundry.enums import (
    FeedMethod,
    Frequency,
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
    Geography,
    IngestionFeed,
    IngestionFeedMember,
    IngestionRunLog,
    IngestionRunLogMember,
    Observation,
    Provider,
    ProviderCatalog,
    Series,
    Indicator,
    IndicatorVariant,
    SeriesHierarchyEdge,
    SeriesSource,
)
from macro_foundry.schemas import ConceptCreate, SeriesCreate, IndicatorCreate
from macro_foundry.services.registration import (
    ensure_series_embedding_current,
    register_concept,
    register_indicator,
    register_series,
)

_PROVIDER_NAME = "Macro Foundry Debug Provider"
_CATALOG_NAME = "Debug smoke catalog"
_CONCEPT_CODE = "DEBUG_INDEX"
_FAMILY_CODE = "US_DEBUG_INDEX"
_FEED_ENDPOINT = "/debug/shared-table"
_SERIES_CODES = ("DEBUG_TOTAL_INDEX", "DEBUG_COMPONENT_A_INDEX")


@dataclass(frozen=True, slots=True)
class DebugSmokeBootstrapResult:
    """Summary of the request-centric debug bootstrap."""

    target: EnvTarget
    run_date: date
    feed_members: int
    member_logs: int
    observations: int
    hierarchy_edges: int


async def run_debug_smoke_bootstrap(
    *,
    target: EnvTarget = EnvTarget.DEV,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
    run_date: date | None = None,
) -> DebugSmokeBootstrapResult:
    """Initialize a minimal request-centric ingestion and hierarchy smoke set."""

    resolved_run_date = run_date or date.today()
    managed_engine = None

    if session_factory is None:
        managed_engine = create_async_engine_for_url(app_url_for_target(target))
        session_factory = create_session_factory(managed_engine)

    try:
        async with session_factory() as session:
            try:
                result = await _run_debug_smoke_transaction(
                    session,
                    target=target,
                    run_date=resolved_run_date,
                )
                await session.commit()
                return result
            except Exception:
                await session.rollback()
                raise
    finally:
        if managed_engine is not None:
            await managed_engine.dispose()


async def _run_debug_smoke_transaction(
    session: AsyncSession,
    *,
    target: EnvTarget,
    run_date: date,
) -> DebugSmokeBootstrapResult:
    geography = await session.scalar(select(Geography).where(Geography.code == "USA"))
    if geography is None:
        raise ValueError("USA geography is missing; run macrodb seed before debug bootstrap")

    provider = await _get_or_create_provider(session)
    catalog = await _get_or_create_catalog(session, provider)
    concept = await _get_or_create_concept(session)
    family = await _get_or_create_family(session, concept=concept, geography=geography)
    series = [
        await _get_or_create_series(session, code=code, geography=geography)
        for code in _SERIES_CODES
    ]
    for item in series:
        await _get_or_create_family_member(session, family=family, series=item)
    series = [
        await ensure_series_embedding_current(session, item)
        for item in series
    ]

    sources = [
        await _get_or_create_source(session, catalog=catalog, series=item, order=order)
        for order, item in enumerate(series, start=1)
    ]
    feed = await _get_or_create_feed(session)
    members = [
        await _get_or_create_feed_member(session, feed=feed, source=source, order=order)
        for order, source in enumerate(sources, start=1)
    ]

    edge = await _get_or_create_hierarchy_edge(session, parent=series[0], child=series[1])
    run_log = IngestionRunLog(
        ingestion_feed_id=feed.id,
        started_at=datetime.now(timezone.utc),
        finished_at=datetime.now(timezone.utc),
        status=IngestionRunStatus.SUCCESS,
        rows_fetched=2,
        rows_inserted=2,
        rows_skipped=0,
        triggered_by=IngestionTriggeredBy.MANUAL,
        parameters={"dataset": "debug-smoke", "run_date": run_date.isoformat()},
        notes="debug smoke shared request",
    )
    session.add(run_log)
    await session.flush()

    member_logs = []
    for order, member in enumerate(members, start=1):
        member_log = IngestionRunLogMember(
            ingestion_run_log_id=run_log.id,
            ingestion_feed_member_id=member.id,
            status=IngestionRunStatus.SUCCESS,
            rows_fetched=1,
            rows_inserted=1,
            rows_skipped=0,
            diagnostics={"selector_type": "json_path", "row": order - 1},
            notes="debug smoke member outcome",
        )
        session.add(member_log)
        member_logs.append(member_log)
    await session.flush()

    statement = insert(Observation).values(
        [
            {
                "series_id": series[0].id,
                "period_start": run_date,
                "period_end": run_date,
                "value": Decimal("100.0"),
                "vintage_date": run_date,
                "ingestion_run_log_member_id": member_logs[0].id,
                "computation_run_log_id": None,
            },
            {
                "series_id": series[1].id,
                "period_start": run_date,
                "period_end": run_date,
                "value": Decimal("40.0"),
                "vintage_date": run_date,
                "ingestion_run_log_member_id": member_logs[1].id,
                "computation_run_log_id": None,
            },
        ],
    )
    excluded = statement.excluded
    statement = statement.on_conflict_do_update(
        index_elements=[Observation.series_id, Observation.period_start, Observation.vintage_date],
        set_={
            "period_end": excluded.period_end,
            "value": excluded.value,
            "ingestion_run_log_member_id": excluded.ingestion_run_log_member_id,
            "computation_run_log_id": None,
        },
    )
    await session.execute(statement)

    return DebugSmokeBootstrapResult(
        target=target,
        run_date=run_date,
        feed_members=len(members),
        member_logs=len(member_logs),
        observations=2,
        hierarchy_edges=1 if edge is not None else 0,
    )


async def _get_or_create_provider(session: AsyncSession) -> Provider:
    provider = await session.scalar(select(Provider).where(Provider.name == _PROVIDER_NAME))
    if provider is None:
        provider = Provider(
            name=_PROVIDER_NAME,
            type=ProviderType.INTERNAL,
            notes="Local debug bootstrap provider.",
            is_active=True,
        )
        session.add(provider)
        await session.flush()
    return provider


async def _get_or_create_catalog(session: AsyncSession, provider: Provider) -> ProviderCatalog:
    catalog = await session.scalar(
        select(ProviderCatalog).where(
            ProviderCatalog.provider_id == provider.id,
            ProviderCatalog.name == _CATALOG_NAME,
        ),
    )
    if catalog is None:
        catalog = ProviderCatalog(
            provider_id=provider.id,
            name=_CATALOG_NAME,
            is_placeholder=True,
        )
        session.add(catalog)
        await session.flush()
    return catalog


async def _get_or_create_concept(session: AsyncSession) -> Concept:
    concept = await session.scalar(select(Concept).where(Concept.code == _CONCEPT_CODE))
    if concept is None:
        concept = await register_concept(
            session,
            ConceptCreate(
                code=_CONCEPT_CODE,
                name="Debug index",
                description="Synthetic concept for request-centric debug bootstrap inspection.",
            ),
        )
    return concept


async def _get_or_create_family(
    session: AsyncSession,
    *,
    concept: Concept,
    geography: Geography,
) -> Indicator:
    family = await session.scalar(select(Indicator).where(Indicator.code == _FAMILY_CODE))
    if family is None:
        family = await register_indicator(
            session,
            IndicatorCreate(
                code=_FAMILY_CODE,
                name="United States debug index",
                concept_id=concept.id,
                geography_id=geography.id,
            ),
        )
    return family


async def _get_or_create_series(
    session: AsyncSession,
    *,
    code: str,
    geography: Geography,
) -> Series:
    series = await session.scalar(select(Series).where(Series.code == code))
    if series is None:
        series = await register_series(
            session,
            SeriesCreate(
                code=code,
                name=code.replace("_", " ").title(),
                origin_type=OriginType.INGESTED,
                geography_id=geography.id,
                frequency=Frequency.DAILY,
                temporal_stock_flow=TemporalStockFlow.INDEX,
                unit_kind=UnitKind.INDEX,
                unit_scale=UnitScale.ONE,
                measure=Measure.LEVEL,
                annualized=False,
                seasonal_adjustment=SeasonalAdjustment.NSA,
                is_active=True,
            ),
        )
    return series


async def _get_or_create_family_member(
    session: AsyncSession,
    *,
    family: Indicator,
    series: Series,
) -> IndicatorVariant:
    member = await session.scalar(
        select(IndicatorVariant).where(IndicatorVariant.series_id == series.id),
    )
    if member is None:
        member = IndicatorVariant(
            indicator_id=family.id,
            series_id=series.id,
            label=series.name,
            is_default=series.code == "DEBUG_TOTAL_INDEX",
        )
        session.add(member)
        await session.flush()
    return member


async def _get_or_create_source(
    session: AsyncSession,
    *,
    catalog: ProviderCatalog,
    series: Series,
    order: int,
) -> SeriesSource:
    source = await session.scalar(
        select(SeriesSource).where(
            SeriesSource.series_id == series.id,
            SeriesSource.provider_catalog_id == catalog.id,
        ),
    )
    if source is None:
        source = SeriesSource(
            series_id=series.id,
            provider_catalog_id=catalog.id,
            external_name=f"Debug smoke row {order}",
            ref_url="https://example.test/macro-foundry/debug-smoke",
            priority=1,
            provider_role=ProviderRole.INTERNAL,
        )
        session.add(source)
        await session.flush()
    return source


async def _get_or_create_feed(session: AsyncSession) -> IngestionFeed:
    feed = await session.scalar(select(IngestionFeed).where(IngestionFeed.endpoint_url == _FEED_ENDPOINT))
    if feed is None:
        feed = IngestionFeed(
            feed_method=FeedMethod.API,
            endpoint_url=_FEED_ENDPOINT,
            request_params={"dataset": "debug-smoke"},
            response_mapping={"data_path": "rows"},
            is_active=True,
        )
        session.add(feed)
        await session.flush()
    return feed


async def _get_or_create_feed_member(
    session: AsyncSession,
    *,
    feed: IngestionFeed,
    source: SeriesSource,
    order: int,
) -> IngestionFeedMember:
    member = await session.scalar(
        select(IngestionFeedMember).where(IngestionFeedMember.series_source_id == source.id),
    )
    if member is None:
        member = IngestionFeedMember(
            ingestion_feed_id=feed.id,
            series_source_id=source.id,
            selector_type="json_path",
            selector_config={"path": f"$.rows[{order - 1}].value"},
            execution_order=order,
            is_active=True,
        )
        session.add(member)
        await session.flush()
    return member


async def _get_or_create_hierarchy_edge(
    session: AsyncSession,
    *,
    parent: Series,
    child: Series,
) -> SeriesHierarchyEdge:
    edge = await session.scalar(
        select(SeriesHierarchyEdge).where(
            SeriesHierarchyEdge.parent_series_id == parent.id,
            SeriesHierarchyEdge.child_series_id == child.id,
        ),
    )
    if edge is None:
        edge = SeriesHierarchyEdge(
            parent_series_id=parent.id,
            child_series_id=child.id,
            sort_order=1,
            notes="Debug smoke parent to component hierarchy.",
        )
        session.add(edge)
        await session.flush()
    return edge


__all__ = ["DebugSmokeBootstrapResult", "run_debug_smoke_bootstrap"]
