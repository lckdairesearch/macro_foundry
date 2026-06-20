"""Curated first-pass FRED U.S. macro bootstrap, re-grained onto the V8 tree.

The original bootstrap materialized the V7 conceptual spine
(concept -> indicator -> indicator_variant -> series) that ADR 0025 dropped. This
rebuild attaches each curated series directly to its most-specific
`kind=concept` node of the `categories` tree (`series.category_id`), minting a
concept under the seeded subdomain skeleton when one does not yet exist (ADR
0025 §3, ADR 0026 §5: concepts accrete; no placeholders). The derived "indicator"
grain (`US_CPI`) is now the query `(category_id, geography_id)` — not a stored row.

The provider / catalog / series_source / ingestion_feed / observation machinery
is unchanged from the V7 preset; only the concept/attachment layer moved.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from importlib.metadata import PackageNotFoundError, version
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from macro_foundry.config import settings
from macro_foundry.db import (
    EnvTarget,
    app_url_for_target,
    create_async_engine_for_url,
    create_session_factory,
)
from macro_foundry.enums import (
    FeedMethod,
    Frequency,
    IngestionTriggeredBy,
    Measure,
    MeasureHorizon,
    OriginType,
    PriceBasis,
    ProviderRole,
    ProviderType,
    ReferenceKind,
    SeasonalAdjustment,
    TemporalStockFlow,
    UnitKind,
    UnitScale,
)
from macro_foundry.ingestion.providers.fred import FredClient, FredClientProtocol, FredSeriesMetadata
from macro_foundry.ingestion.runtime import execute_feed
from macro_foundry.models import (
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
from macro_foundry.schemas import (
    IngestionFeedCreate,
    IngestionFeedMemberCreate,
    ProviderCatalogCreate,
    ProviderCreate,
    SeriesCreate,
    SeriesSourceCreate,
)
from macro_foundry.seed._shared import assign_if_changed
from macro_foundry.services.registration import (
    ensure_series_embedding_current,
    register_concept_node,
    register_series,
)

_FRED_PROVIDER_NAME = "USA FRED"
_FRED_CATALOG_NAME = "FRED default catalog"
_FRED_CREDENTIALS_REF = "FRED_API_KEY"
_FRED_ENDPOINT_PATH = "/series/observations"
_FRED_METADATA_ENDPOINT_PATH = "/series"
_FRED_DOC_URL = "https://fred.stlouisfed.org/docs/api/fred/"
_FRED_HOMEPAGE_URL = "https://fred.stlouisfed.org/"
_FRED_BASE_URL = "https://api.stlouisfed.org/fred"
_FRED_SCHEDULE = "TZ=America/New_York 0 8 * * *"
_FRED_MISSING_VALUE_TOKENS = [".", ""]
_FRED_FREQUENCY_MAP = {
    "A": Frequency.ANNUAL.value,
    "D": Frequency.DAILY.value,
    "M": Frequency.MONTHLY.value,
    "Q": Frequency.QUARTERLY.value,
    "SA": Frequency.SEMI_ANNUAL.value,
    "W": Frequency.WEEKLY.value,
}


@dataclass(frozen=True, slots=True)
class RawSeriesSpec:
    """Curated raw FRED series definition, attached to a V8 concept node.

    `concept_code` / `concept_parent_code` name the `kind=concept` node the series
    attaches to and the seeded subdomain it lives under.
    """

    concept_code: str
    concept_name: str
    concept_description: str
    concept_parent_code: str
    series_code: str
    series_name: str
    series_alt_name: tuple[str, ...]
    series_description: str
    external_code: str
    frequency: Frequency
    temporal_stock_flow: TemporalStockFlow
    unit_kind: UnitKind
    unit_scale: UnitScale
    unit_label: str | None
    price_basis: PriceBasis | None
    currency_code: str | None
    measure: Measure
    measure_horizon: MeasureHorizon | None
    annualized: bool
    seasonal_adjustment: SeasonalAdjustment
    reference_kind: ReferenceKind | None
    reference_year: int | None
    reference_label: str | None


@dataclass(frozen=True, slots=True)
class FredImportOutcome:
    """Summary of one FRED raw-series latest-snapshot import."""

    series_code: str
    external_code: str
    metadata: FredSeriesMetadata
    rows_fetched: int
    rows_written: int
    rows_skipped: int
    run_log_id: Any


@dataclass(frozen=True, slots=True)
class FredUsMacroBootstrapResult:
    """End-to-end bootstrap summary returned to the CLI and tests."""

    target: EnvTarget
    run_date: date
    raw_imports: tuple[FredImportOutcome, ...]


@dataclass(frozen=True, slots=True)
class FredUsMacroResetResult:
    """Summary of removing the curated first-pass FRED preset.

    Concept nodes are part of the `categories` tree (seeded or accreted) and are
    deliberately *not* deleted by a preset reset — a reset removes the ingested
    series and everything hanging off them, leaving the taxonomy intact so a
    subsequent reseed + rebootstrap is a clean no-op on the tree.
    """

    target: EnvTarget
    observations_deleted: int
    ingestion_run_logs_deleted: int
    ingestion_feeds_deleted: int
    series_sources_deleted: int
    series_deleted: int


@dataclass(slots=True)
class PreparedRawSeries:
    """Upserted raw-series rows needed for import execution."""

    spec: RawSeriesSpec
    series: Series
    source: SeriesSource
    feed: IngestionFeed
    feed_member: IngestionFeedMember


@dataclass(slots=True)
class FredRuntimeConfig:
    """Resolved runtime config for the provider-backed FRED client."""

    api_key: str
    base_url: str


RAW_SERIES_SPECS: tuple[RawSeriesSpec, ...] = (
    RawSeriesSpec(
        concept_code="GDP_NOMINAL",
        concept_name="GDP Nominal",
        concept_description="Gross domestic product measured at current market prices, without adjustment for inflation.",
        concept_parent_code="GDP_AND_GROWTH",
        series_code="US_GDP_NOMINAL_Q_SAAR",
        series_name="USA – Gross Domestic Product, Nominal, Seasonally Adjusted Annual Rate, Billions of Dollars",
        series_alt_name=(
            "United States Gross Domestic Product, Nominal Level",
            "Gross Domestic Product",
            "Nominal GDP",
        ),
        series_description="Quarterly level of nominal gross domestic product for the United States, expressed at a seasonally adjusted annual rate in billions of current U.S. dollars. Published by the U.S. Bureau of Economic Analysis as part of the National Income and Product Accounts. Nominal GDP measures the total market value of goods and services produced in the United States without adjusting for changes in prices.",
        external_code="GDP",
        frequency=Frequency.QUARTERLY,
        temporal_stock_flow=TemporalStockFlow.FLOW,
        unit_kind=UnitKind.CURRENCY,
        unit_scale=UnitScale.BILLION,
        unit_label=None,
        price_basis=PriceBasis.NOMINAL,
        currency_code="USD",
        measure=Measure.LEVEL,
        measure_horizon=None,
        annualized=True,
        seasonal_adjustment=SeasonalAdjustment.SAAR,
        reference_kind=None,
        reference_year=None,
        reference_label=None,
    ),
    RawSeriesSpec(
        concept_code="GDP_REAL",
        concept_name="GDP Real",
        concept_description="Gross domestic product adjusted for inflation, expressed in constant (chained) prices.",
        concept_parent_code="GDP_AND_GROWTH",
        series_code="US_GDP_REAL_Q_SAAR",
        series_name="USA – Gross Domestic Product, Real, Seasonally Adjusted Annual Rate, Billions of Chained 2017 Dollars",
        series_alt_name=(
            "United States Gross Domestic Product, Real Level",
            "Real Gross Domestic Product",
            "Real GDP",
        ),
        series_description="Quarterly level of real gross domestic product for the United States, expressed at a seasonally adjusted annual rate in billions of chained 2017 dollars. Published by the U.S. Bureau of Economic Analysis as part of the National Income and Product Accounts. Real GDP measures the total value of goods and services produced in the United States after adjusting for changes in prices.",
        external_code="GDPC1",
        frequency=Frequency.QUARTERLY,
        temporal_stock_flow=TemporalStockFlow.FLOW,
        unit_kind=UnitKind.CURRENCY,
        unit_scale=UnitScale.BILLION,
        unit_label=None,
        price_basis=PriceBasis.REAL,
        currency_code="USD",
        measure=Measure.LEVEL,
        measure_horizon=None,
        annualized=True,
        seasonal_adjustment=SeasonalAdjustment.SAAR,
        reference_kind=ReferenceKind.CONSTANT_PRICES,
        reference_year=2017,
        reference_label="Chained 2017 dollars",
    ),
    RawSeriesSpec(
        concept_code="CPI_ALL_ITEMS",
        concept_name="CPI All Items",
        concept_description="Consumer price index covering the full basket of goods and services (headline inflation).",
        concept_parent_code="CONSUMER_PRICES",
        series_code="US_CPI_HEADLINE_M_NSA",
        series_name="USA – Consumer Price Index for All Urban Consumers: All Items in U.S. City Average",
        series_alt_name=(
            "Consumer Price Index for All Urban Consumers: All Items in U.S. City Average",
            "United States CPI Headline, Level",
            "CPI-U All Items",
            "Headline CPI",
        ),
        series_description="Monthly index level of the Consumer Price Index for All Urban Consumers (CPI-U) covering all items, U.S. city average. Published by the U.S. Bureau of Labor Statistics. Not seasonally adjusted. Reference base period 1982-84 = 100.",
        external_code="CPIAUCNS",
        frequency=Frequency.MONTHLY,
        temporal_stock_flow=TemporalStockFlow.INDEX,
        unit_kind=UnitKind.INDEX,
        unit_scale=UnitScale.ONE,
        unit_label=None,
        price_basis=None,
        currency_code=None,
        measure=Measure.LEVEL,
        measure_horizon=None,
        annualized=False,
        seasonal_adjustment=SeasonalAdjustment.NSA,
        reference_kind=ReferenceKind.INDEX_BASE,
        reference_year=None,
        reference_label="1982-1984=100",
    ),
    RawSeriesSpec(
        concept_code="CPI_CORE",
        concept_name="CPI Core",
        concept_description="Consumer price index excluding the volatile food and energy components, used to gauge underlying (core) inflation. A cross-country generalizable concept; the exact exclusion list is a series-level methodology detail (ADR 0026 §5).",
        concept_parent_code="CONSUMER_PRICES",
        series_code="US_CPI_CORE_M_SA",
        series_name="USA – Consumer Price Index for All Urban Consumers: All Items Less Food and Energy in U.S. City Average",
        series_alt_name=(
            "Consumer Price Index for All Urban Consumers: All Items Less Food and Energy in U.S. City Average",
            "United States CPI Core, Level",
            "Core CPI",
            "CPI-U Less Food and Energy",
        ),
        series_description="Monthly index level of the Consumer Price Index for All Urban Consumers (CPI-U) covering all items excluding food and energy (\"core CPI\"), U.S. city average. Seasonally adjusted. Reference base period 1982-84 = 100. Core CPI tracks underlying inflation by removing the most volatile components of the headline basket.",
        external_code="CPILFESL",
        frequency=Frequency.MONTHLY,
        temporal_stock_flow=TemporalStockFlow.INDEX,
        unit_kind=UnitKind.INDEX,
        unit_scale=UnitScale.ONE,
        unit_label=None,
        price_basis=None,
        currency_code=None,
        measure=Measure.LEVEL,
        measure_horizon=None,
        annualized=False,
        seasonal_adjustment=SeasonalAdjustment.SA,
        reference_kind=ReferenceKind.INDEX_BASE,
        reference_year=None,
        reference_label="1982-1984=100",
    ),
)


async def run_fred_us_macro_bootstrap(
    *,
    target: EnvTarget = EnvTarget.DEV,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
    client: FredClientProtocol | None = None,
    run_date: date | None = None,
) -> FredUsMacroBootstrapResult:
    """Run the curated FRED U.S. macro bootstrap against the selected database."""

    resolved_run_date = run_date or date.today()
    code_version = _current_code_version()
    managed_engine = None

    if session_factory is None:
        managed_engine = create_async_engine_for_url(app_url_for_target(target))
        session_factory = create_session_factory(managed_engine)

    try:
        return await _run_bootstrap_transaction(
            session_factory=session_factory,
            client=client,
            target=target,
            run_date=resolved_run_date,
            code_version=code_version,
        )
    finally:
        if managed_engine is not None:
            await managed_engine.dispose()


async def reset_fred_us_macro_bootstrap(
    *,
    target: EnvTarget = EnvTarget.DEV,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
) -> FredUsMacroResetResult:
    """Delete the curated first-pass FRED preset rows while preserving the taxonomy."""

    managed_engine = None
    if session_factory is None:
        managed_engine = create_async_engine_for_url(app_url_for_target(target))
        session_factory = create_session_factory(managed_engine)

    try:
        async with session_factory() as session:
            try:
                result = await _reset_bootstrap_transaction(session, target=target)
                await session.commit()
                return result
            except Exception:
                await session.rollback()
                raise
    finally:
        if managed_engine is not None:
            await managed_engine.dispose()


async def _run_bootstrap_transaction(
    *,
    session_factory: async_sessionmaker[AsyncSession],
    client: FredClientProtocol | None,
    target: EnvTarget,
    run_date: date,
    code_version: str | None,
) -> FredUsMacroBootstrapResult:
    async with session_factory() as session:
        try:
            usa = await _require_usa_geography(session)
            provider = await _upsert_fred_provider(session)
            catalog = await _upsert_fred_catalog(session, provider=provider)
            runtime_client = client
            owned_client: FredClient | None = None
            if runtime_client is None:
                runtime_config = _resolve_fred_runtime_config(provider)
                owned_client = FredClient(
                    api_key=runtime_config.api_key,
                    base_url=runtime_config.base_url,
                )
                runtime_client = owned_client

            try:
                prepared_raw_series: list[PreparedRawSeries] = []
                for spec in RAW_SERIES_SPECS:
                    prepared = await _prepare_series_catalog(
                        session,
                        spec=spec,
                        geography=usa,
                        provider_catalog=catalog,
                    )
                    prepared_raw_series.append(prepared)

                raw_results: list[FredImportOutcome] = []
                for prepared in prepared_raw_series:
                    outcome = await _import_fred_latest_snapshot(
                        session,
                        client=runtime_client,
                        prepared=prepared,
                        run_date=run_date,
                        code_version=code_version,
                        triggered_by=IngestionTriggeredBy.MANUAL,
                    )
                    _sync_raw_metadata_from_fred(
                        prepared.series,
                        prepared.source,
                        metadata=outcome.metadata,
                    )
                    raw_results.append(outcome)
            finally:
                if owned_client is not None:
                    await owned_client.aclose()

            await session.commit()
            return FredUsMacroBootstrapResult(
                target=target,
                run_date=run_date,
                raw_imports=tuple(raw_results),
            )
        except Exception:
            await session.rollback()
            raise


async def _reset_bootstrap_transaction(
    session: AsyncSession,
    *,
    target: EnvTarget,
) -> FredUsMacroResetResult:
    series_codes = _all_bootstrap_series_codes()
    series_rows = (
        await session.execute(
            select(Series.id, Series.code).where(Series.code.in_(series_codes)),
        )
    ).all()
    if not series_rows:
        return FredUsMacroResetResult(
            target=target,
            observations_deleted=0,
            ingestion_run_logs_deleted=0,
            ingestion_feeds_deleted=0,
            series_sources_deleted=0,
            series_deleted=0,
        )

    series_ids = {series_id for series_id, _ in series_rows}

    source_ids = set(
        (
            await session.execute(
                select(SeriesSource.id).where(SeriesSource.series_id.in_(series_ids)),
            )
        ).scalars().all()
    )
    feed_ids = set(
        (
            await session.execute(
                select(IngestionFeedMember.ingestion_feed_id).where(IngestionFeedMember.series_source_id.in_(source_ids)),
            )
        ).scalars().all()
    )
    ingestion_run_log_ids = set(
        (
            await session.execute(
                select(IngestionRunLog.id).where(IngestionRunLog.ingestion_feed_id.in_(feed_ids)),
            )
        ).scalars().all()
    )

    observations_deleted = await _execute_delete(
        session,
        delete(Observation).where(Observation.series_id.in_(series_ids)),
    )
    await _execute_delete(
        session,
        delete(IngestionRunLogMember).where(IngestionRunLogMember.ingestion_run_log_id.in_(ingestion_run_log_ids)),
    )
    ingestion_run_logs_deleted = await _execute_delete(
        session,
        delete(IngestionRunLog).where(IngestionRunLog.ingestion_feed_id.in_(feed_ids)),
    )
    ingestion_feeds_deleted = await _execute_delete(
        session,
        delete(IngestionFeed).where(IngestionFeed.id.in_(feed_ids)),
    )
    series_sources_deleted = await _execute_delete(
        session,
        delete(SeriesSource).where(SeriesSource.id.in_(source_ids)),
    )
    series_deleted = await _execute_delete(
        session,
        delete(Series).where(Series.id.in_(series_ids)),
    )

    return FredUsMacroResetResult(
        target=target,
        observations_deleted=observations_deleted,
        ingestion_run_logs_deleted=ingestion_run_logs_deleted,
        ingestion_feeds_deleted=ingestion_feeds_deleted,
        series_sources_deleted=series_sources_deleted,
        series_deleted=series_deleted,
    )


async def _prepare_series_catalog(
    session: AsyncSession,
    *,
    spec: RawSeriesSpec,
    geography: Geography,
    provider_catalog: ProviderCatalog,
) -> PreparedRawSeries:
    concept = await register_concept_node(
        session,
        code=spec.concept_code,
        name=spec.concept_name,
        parent_code=spec.concept_parent_code,
        description=spec.concept_description,
    )

    raw_series = await _upsert_series(
        session,
        payload=_raw_series_payload(spec, geography_id=geography.id, category_id=concept.id),
    )
    raw_series = await ensure_series_embedding_current(session, raw_series)
    source = await _upsert_series_source(
        session,
        payload=SeriesSourceCreate(
            series_id=raw_series.id,
            provider_catalog_id=provider_catalog.id,
            external_code=spec.external_code,
            priority=1,
            provider_role=ProviderRole.REDISTRIBUTOR,
        ).model_dump(),
    )
    feed = await _upsert_ingestion_feed(
        session,
        payload=IngestionFeedCreate(
            feed_method=FeedMethod.API,
            endpoint_url=_FRED_ENDPOINT_PATH,
            response_mapping={"date_field": "date", "value_field": "value"},
            cron_schedule=_FRED_SCHEDULE,
            is_active=True,
        ).model_dump(),
        series_source_id=source.id,
    )
    feed_member = await _upsert_ingestion_feed_member(
        session,
        payload=IngestionFeedMemberCreate(
            ingestion_feed_id=feed.id,
            series_source_id=source.id,
            selector_type="json_path",
            selector_config=_fred_json_path_selector_config(spec),
            is_active=True,
        ).model_dump(),
    )

    return PreparedRawSeries(spec=spec, series=raw_series, source=source, feed=feed, feed_member=feed_member)


def _fred_json_path_selector_config(spec: RawSeriesSpec) -> dict[str, Any]:
    return {
        "series_id": spec.external_code,
        "metadata_endpoint": _FRED_METADATA_ENDPOINT_PATH,
        "observations_endpoint": _FRED_ENDPOINT_PATH,
        "records_path": "observations",
        "period_anchor_field": "date",
        "value_field": "value",
        "missing_value_tokens": _FRED_MISSING_VALUE_TOKENS,
        "frequency": spec.frequency.value,
        "frequency_map": _FRED_FREQUENCY_MAP,
    }


async def _import_fred_latest_snapshot(
    session: AsyncSession,
    *,
    client: FredClientProtocol,
    prepared: PreparedRawSeries,
    run_date: date,
    code_version: str | None,
    triggered_by: IngestionTriggeredBy,
) -> FredImportOutcome:
    config = prepared.feed_member.selector_config or {}
    external_code = str(config.get("series_id") or prepared.spec.external_code)
    metadata_endpoint = str(config.get("metadata_endpoint") or _FRED_METADATA_ENDPOINT_PATH)
    observations_endpoint = str(config.get("observations_endpoint") or prepared.feed.endpoint_url or _FRED_ENDPOINT_PATH)
    observation_start = await _resolve_observation_start(
        session,
        series_id=prepared.series.id,
        frequency=prepared.spec.frequency,
        request_params=prepared.feed.request_params or {},
    )

    metadata = await client.fetch_series_metadata(
        external_code,
        endpoint_path=metadata_endpoint,
    )
    if metadata.frequency is not prepared.spec.frequency:
        raise ValueError(
            f"FRED frequency {metadata.frequency.value!r} for {external_code!r} does not match "
            f"curated series frequency {prepared.spec.frequency.value!r}",
        )

    fetched_rows = await client.fetch_series_observations(
        external_code,
        observation_start=observation_start,
        endpoint_path=observations_endpoint,
    )
    payload = {
        "observations": [
            {
                "date": row.period_anchor.isoformat(),
                "value": None if row.value is None else str(row.value),
            }
            for row in fetched_rows
        ],
    }
    execution = await execute_feed(
        session,
        prepared.feed.id,
        payload=payload,
        run_date=run_date,
        triggered_by=triggered_by,
        code_version=code_version,
        parameters=_build_fred_run_parameters(
            external_code=external_code,
            observation_start=observation_start,
            run_date=run_date,
        ),
    )

    return FredImportOutcome(
        series_code=prepared.series.code,
        external_code=external_code,
        metadata=metadata,
        rows_fetched=execution.rows_fetched,
        rows_written=execution.rows_inserted,
        rows_skipped=execution.rows_skipped,
        run_log_id=execution.run_log_id,
    )


async def _resolve_observation_start(
    session: AsyncSession,
    *,
    series_id: Any,
    frequency: Frequency,
    request_params: dict[str, Any],
) -> date | None:
    latest_period_start = await session.scalar(
        select(func.max(Observation.period_start)).where(Observation.series_id == series_id),
    )
    if latest_period_start is None:
        return None

    overlap = request_params.get("overlap")
    if overlap is None:
        unit, value = _default_overlap_for_frequency(frequency)
    else:
        unit = str(overlap["unit"])
        value = int(overlap["value"])

    return _shift_period_start(latest_period_start, unit=unit, value=-value)


def _default_overlap_for_frequency(frequency: Frequency) -> tuple[str, int]:
    mapping = {
        Frequency.DAILY: ("days", 35),
        Frequency.WEEKLY: ("weeks", 12),
        Frequency.MONTHLY: ("months", 18),
        Frequency.QUARTERLY: ("quarters", 8),
        Frequency.SEMI_ANNUAL: ("quarters", 6),
        Frequency.ANNUAL: ("years", 5),
    }
    return mapping[frequency]


def _shift_period_start(anchor: date, *, unit: str, value: int) -> date:
    normalized_unit = unit.lower()
    if normalized_unit in {"days", "day"}:
        from datetime import timedelta

        return anchor + timedelta(days=value)
    if normalized_unit in {"weeks", "week"}:
        from datetime import timedelta

        return anchor + timedelta(weeks=value)
    if normalized_unit in {"months", "month"}:
        return _shift_months(anchor, value)
    if normalized_unit in {"quarters", "quarter"}:
        return _shift_months(anchor, value * 3)
    if normalized_unit in {"years", "year"}:
        return _shift_months(anchor, value * 12)
    raise ValueError(f"Unsupported overlap unit {unit!r}")


def _shift_months(anchor: date, months: int) -> date:
    total_months = (anchor.year * 12 + (anchor.month - 1)) + months
    year = total_months // 12
    month = total_months % 12 + 1
    return date(year, month, 1)


def _build_fred_run_parameters(
    *,
    external_code: str,
    observation_start: date | None,
    run_date: date,
) -> dict[str, str]:
    payload = {
        "series_id": external_code,
        "snapshot_vintage_date": run_date.isoformat(),
    }
    if observation_start is not None:
        payload["observation_start"] = observation_start.isoformat()
    return payload


def _sync_raw_metadata_from_fred(
    series: Series,
    source: SeriesSource,
    *,
    metadata: Any,
) -> None:
    if source.external_name != metadata.title:
        source.external_name = metadata.title
    if series.start_date != metadata.observation_start:
        series.start_date = metadata.observation_start
    if source.start_date != metadata.observation_start:
        source.start_date = metadata.observation_start


async def _require_usa_geography(session: AsyncSession) -> Geography:
    usa = await session.scalar(select(Geography).where(Geography.code == "USA"))
    if usa is None:
        raise ValueError("USA geography is missing; run macrodb seed before bootstrap")
    return usa


async def _upsert_fred_provider(session: AsyncSession) -> Provider:
    payload = ProviderCreate(
        name=_FRED_PROVIDER_NAME,
        alt_name=["Federal Reserve Economic Data"],
        type=ProviderType.OFFICIAL,
        homepage_url=_FRED_HOMEPAGE_URL,
        doc_url=_FRED_DOC_URL,
        base_url=_FRED_BASE_URL,
        credentials_ref=_FRED_CREDENTIALS_REF,
        is_active=True,
    ).model_dump()
    provider = await session.scalar(select(Provider).where(Provider.name == _FRED_PROVIDER_NAME))
    if provider is None:
        provider = Provider(**payload)
        session.add(provider)
        await session.flush()
        return provider

    assign_if_changed(
        provider,
        payload,
        ("alt_name", "type", "homepage_url", "doc_url", "base_url", "credentials_ref", "is_active"),
    )
    await session.flush()
    return provider


async def _upsert_fred_catalog(
    session: AsyncSession,
    *,
    provider: Provider,
) -> ProviderCatalog:
    payload = ProviderCatalogCreate(
        provider_id=provider.id,
        name=_FRED_CATALOG_NAME,
        catalog_url=_FRED_HOMEPAGE_URL,
        doc_url=_FRED_DOC_URL,
        notes="Placeholder catalog for the unified FRED series namespace.",
        is_placeholder=True,
    ).model_dump()
    rows = (
        await session.execute(
            select(ProviderCatalog).where(
                ProviderCatalog.provider_id == provider.id,
                ProviderCatalog.name == _FRED_CATALOG_NAME,
            ),
        )
    ).scalars().all()
    if len(rows) > 1:
        raise ValueError("Multiple FRED default catalogs found; expected one natural-key match")
    if not rows:
        catalog = ProviderCatalog(**payload)
        session.add(catalog)
        await session.flush()
        return catalog

    catalog = rows[0]
    assign_if_changed(
        catalog,
        payload,
        ("catalog_url", "doc_url", "notes", "is_placeholder"),
    )
    await session.flush()
    return catalog


async def _upsert_series(
    session: AsyncSession,
    *,
    payload: dict[str, Any],
) -> Series:
    series = await session.scalar(select(Series).where(Series.code == payload["code"]))
    if series is None:
        return await register_series(
            session,
            SeriesCreate.model_validate(payload),
        )
    assign_if_changed(
        series,
        payload,
        (
            "name",
            "alt_name",
            "description",
            "origin_type",
            "category_id",
            "geography_id",
            "frequency",
            "temporal_stock_flow",
            "unit_kind",
            "unit_scale",
            "unit_label",
            "price_basis",
            "currency_code",
            "measure",
            "measure_horizon",
            "annualized",
            "seasonal_adjustment",
            "reference_kind",
            "reference_year",
            "reference_label",
            "is_active",
        ),
    )
    await session.flush()
    return series


async def _upsert_series_source(
    session: AsyncSession,
    *,
    payload: dict[str, Any],
) -> SeriesSource:
    source = await session.scalar(
        select(SeriesSource).where(
            SeriesSource.provider_catalog_id == payload["provider_catalog_id"],
            SeriesSource.external_code == payload["external_code"],
        ),
    )
    if source is None:
        source = SeriesSource(**payload)
        session.add(source)
        await session.flush()
        return source
    assign_if_changed(
        source,
        payload,
        (
            "series_id",
            "external_name",
            "ref_url",
            "priority",
            "provider_role",
            "value_transform",
            "start_date",
            "end_date",
        ),
    )
    await session.flush()
    return source


async def _upsert_ingestion_feed(
    session: AsyncSession,
    *,
    payload: dict[str, Any],
    series_source_id: object,
) -> IngestionFeed:
    rows = (
        await session.execute(
            select(IngestionFeed)
            .join(IngestionFeedMember, IngestionFeedMember.ingestion_feed_id == IngestionFeed.id)
            .where(IngestionFeedMember.series_source_id == series_source_id),
        )
    ).scalars().all()
    if len(rows) > 1:
        raise ValueError("Multiple ingestion feed members found for one series source; expected at most one")
    if not rows:
        feed = IngestionFeed(**payload)
        session.add(feed)
        await session.flush()
        return feed

    feed = rows[0]
    assign_if_changed(
        feed,
        payload,
        (
            "feed_method",
            "endpoint_url",
            "request_params",
            "file_path_pattern",
            "response_mapping",
            "cron_schedule",
            "is_active",
        ),
    )
    await session.flush()
    return feed


async def _upsert_ingestion_feed_member(
    session: AsyncSession,
    *,
    payload: dict[str, Any],
) -> IngestionFeedMember:
    member = await session.scalar(
        select(IngestionFeedMember).where(IngestionFeedMember.series_source_id == payload["series_source_id"]),
    )
    if member is None:
        member = IngestionFeedMember(**payload)
        session.add(member)
        await session.flush()
        return member
    assign_if_changed(
        member,
        payload,
        (
            "ingestion_feed_id",
            "selector_type",
            "selector_config",
            "execution_order",
            "is_active",
        ),
    )
    await session.flush()
    return member


def _raw_series_payload(spec: RawSeriesSpec, *, geography_id: Any, category_id: Any) -> dict[str, Any]:
    return SeriesCreate(
        code=spec.series_code,
        name=spec.series_name,
        alt_name=list(spec.series_alt_name) if spec.series_alt_name else None,
        description=spec.series_description,
        origin_type=OriginType.INGESTED,
        category_id=category_id,
        geography_id=geography_id,
        frequency=spec.frequency,
        temporal_stock_flow=spec.temporal_stock_flow,
        unit_kind=spec.unit_kind,
        unit_scale=spec.unit_scale,
        unit_label=spec.unit_label,
        price_basis=spec.price_basis,
        currency_code=spec.currency_code,
        measure=spec.measure,
        measure_horizon=spec.measure_horizon,
        annualized=spec.annualized,
        seasonal_adjustment=spec.seasonal_adjustment,
        reference_kind=spec.reference_kind,
        reference_year=spec.reference_year,
        reference_label=spec.reference_label,
        is_active=True,
    ).model_dump()


def _current_code_version() -> str | None:
    try:
        return version("macro-foundry")
    except PackageNotFoundError:
        return None


def _resolve_fred_runtime_config(provider: Provider) -> FredRuntimeConfig:
    credentials_ref = provider.credentials_ref
    api_key = settings.resolve_credential_ref(credentials_ref)
    if api_key is None:
        raise ValueError(
            f"Provider {provider.name!r} requires credentials_ref {credentials_ref!r}, but no matching environment value was found",
        )
    return FredRuntimeConfig(
        api_key=api_key,
        base_url=provider.base_url or _FRED_BASE_URL,
    )


def _all_bootstrap_series_codes() -> tuple[str, ...]:
    return tuple(spec.series_code for spec in RAW_SERIES_SPECS)


async def _execute_delete(session: AsyncSession, statement: Any) -> int:
    result = await session.execute(statement)
    return int(result.rowcount or 0)


__all__ = [
    "EnvTarget",
    "FredUsMacroBootstrapResult",
    "FredUsMacroResetResult",
    "RAW_SERIES_SPECS",
    "RawSeriesSpec",
    "reset_fred_us_macro_bootstrap",
    "run_fred_us_macro_bootstrap",
]
