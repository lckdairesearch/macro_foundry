"""Curated first-pass FRED U.S. macro bootstrap."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from importlib.metadata import PackageNotFoundError, version
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from macro_foundry.config import settings
from macro_foundry.db import (
    DatabaseTarget,
    create_async_engine_for_url,
    create_session_factory,
    database_url_for_target,
)
from macro_foundry.enums import (
    ComputationRunStatus,
    ComputationTriggeredBy,
    ExecutionPolicy,
    FeedMethod,
    Frequency,
    IngestionTriggeredBy,
    InputVintagePolicy,
    Measure,
    MeasureHorizon,
    OriginType,
    OutputMode,
    PriceBasis,
    ProviderRole,
    ProviderType,
    ReferenceKind,
    SeasonalAdjustment,
    TemporalStockFlow,
    UnitKind,
    UnitScale,
)
from macro_foundry.ingestion.providers.fred import FredClient, FredClientProtocol
from macro_foundry.ingestion.runners.fred_series import FredImportOutcome, import_fred_latest_snapshot
from macro_foundry.models import (
    ComputationRunLog,
    Concept,
    DerivationInput,
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
    SeriesFamily,
    SeriesFamilyMember,
    SeriesSource,
)
from macro_foundry.schemas import (
    ConceptCreate,
    DerivedSeriesCreate,
    DerivationInputCreate,
    IngestionFeedCreate,
    IngestionFeedMemberCreate,
    ProviderCatalogCreate,
    ProviderCreate,
    SeriesCreate,
    SeriesFamilyCreate,
    SeriesFamilyMemberCreate,
    SeriesSourceCreate,
)
from macro_foundry.seed._shared import assign_if_changed

_FRED_PROVIDER_NAME = "USA FRED"
_FRED_CATALOG_NAME = "FRED default catalog"
_FRED_CREDENTIALS_REF = "FRED_API_KEY"
_FRED_ENDPOINT_PATH = "/series/observations"
_FRED_DOC_URL = "https://fred.stlouisfed.org/docs/api/fred/"
_FRED_HOMEPAGE_URL = "https://fred.stlouisfed.org/"
_FRED_BASE_URL = "https://api.stlouisfed.org/fred"
_FRED_SCHEDULE = "TZ=America/New_York 0 8 * * *"
_YOY_CODE_REF = "macro_foundry.bootstrap.fred_us_macro.compute_yoy_growth"


@dataclass(frozen=True, slots=True)
class RawSeriesSpec:
    """Curated raw FRED series definition for the preset."""

    concept_code: str
    concept_name: str
    concept_description: str
    family_code: str
    family_name: str
    family_description: str
    series_code: str
    series_name: str
    series_description: str
    family_variant: str
    is_primary_family_member: bool
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
    derived_series_code: str
    derived_series_name: str
    derived_series_description: str
    derived_family_variant: str


@dataclass(frozen=True, slots=True)
class DerivedComputationOutcome:
    """Summary of one derived YoY computation pass."""

    series_code: str
    rows_computed: int
    rows_written: int
    rows_skipped: int


@dataclass(frozen=True, slots=True)
class FredUsMacroBootstrapResult:
    """End-to-end bootstrap summary returned to the CLI and tests."""

    database: DatabaseTarget
    run_date: date
    raw_imports: tuple[FredImportOutcome, ...]
    derived_imports: tuple[DerivedComputationOutcome, ...]


@dataclass(frozen=True, slots=True)
class FredUsMacroResetResult:
    """Summary of removing the curated first-pass FRED preset."""

    database: DatabaseTarget
    observations_deleted: int
    ingestion_run_logs_deleted: int
    computation_run_logs_deleted: int
    derivation_inputs_deleted: int
    derived_series_deleted: int
    ingestion_feeds_deleted: int
    series_sources_deleted: int
    family_members_deleted: int
    series_deleted: int
    families_deleted: int
    concepts_deleted: int


@dataclass(slots=True)
class PreparedRawSeries:
    """Upserted raw-series rows needed for import execution."""

    spec: RawSeriesSpec
    series: Series
    source: SeriesSource
    feed: IngestionFeed
    feed_member: IngestionFeedMember


@dataclass(slots=True)
class PreparedDerivedSeries:
    """Upserted derived-series rows needed for YoY computation."""

    spec: RawSeriesSpec
    output_series: Series
    derived_series: DerivedSeries
    input_series: Series


@dataclass(slots=True)
class FredRuntimeConfig:
    """Resolved runtime config for the provider-backed FRED client."""

    api_key: str
    base_url: str


RAW_SERIES_SPECS: tuple[RawSeriesSpec, ...] = (
    RawSeriesSpec(
        concept_code="GDP",
        concept_name="Gross Domestic Product",
        concept_description="Geography-neutral gross domestic product concept.",
        family_code="US_GDP",
        family_name="United States Gross Domestic Product",
        family_description="Curated United States GDP variants.",
        series_code="US_GDP_NOMINAL_Q_SAAR_LEVEL",
        series_name="United States Gross Domestic Product, Nominal Level",
        series_description="Quarterly nominal GDP level imported from FRED ticker GDP.",
        family_variant="Nominal",
        is_primary_family_member=True,
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
        derived_series_code="US_GDP_NOMINAL_Q_SAAR_YOY",
        derived_series_name="United States Gross Domestic Product, Nominal YoY",
        derived_series_description="Year-over-year percent growth computed from nominal GDP levels.",
        derived_family_variant="Nominal YoY",
    ),
    RawSeriesSpec(
        concept_code="GDP",
        concept_name="Gross Domestic Product",
        concept_description="Geography-neutral gross domestic product concept.",
        family_code="US_GDP",
        family_name="United States Gross Domestic Product",
        family_description="Curated United States GDP variants.",
        series_code="US_GDP_REAL_Q_SAAR_LEVEL",
        series_name="United States Gross Domestic Product, Real Level",
        series_description="Quarterly real GDP level imported from FRED ticker GDPC1.",
        family_variant="Real",
        is_primary_family_member=False,
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
        derived_series_code="US_GDP_REAL_Q_SAAR_YOY",
        derived_series_name="United States Gross Domestic Product, Real YoY",
        derived_series_description="Year-over-year percent growth computed from real GDP levels.",
        derived_family_variant="Real YoY",
    ),
    RawSeriesSpec(
        concept_code="CPI",
        concept_name="Consumer Price Index",
        concept_description="Geography-neutral consumer price index concept.",
        family_code="US_CPI",
        family_name="United States Consumer Price Index",
        family_description="Curated United States CPI variants.",
        series_code="US_CPI_HEADLINE_M_NSA_LEVEL",
        series_name="United States CPI Headline, Level",
        series_description="Monthly headline CPI level imported from FRED ticker CPIAUCNS.",
        family_variant="Headline",
        is_primary_family_member=True,
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
        derived_series_code="US_CPI_HEADLINE_M_NSA_YOY",
        derived_series_name="United States CPI Headline, YoY",
        derived_series_description="Year-over-year percent growth computed from headline CPI levels.",
        derived_family_variant="Headline YoY",
    ),
    RawSeriesSpec(
        concept_code="CPI",
        concept_name="Consumer Price Index",
        concept_description="Geography-neutral consumer price index concept.",
        family_code="US_CPI",
        family_name="United States Consumer Price Index",
        family_description="Curated United States CPI variants.",
        series_code="US_CPI_CORE_M_SA_LEVEL",
        series_name="United States CPI Core, Level",
        series_description="Monthly core CPI level imported from FRED ticker CPILFESL.",
        family_variant="Core",
        is_primary_family_member=False,
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
        derived_series_code="US_CPI_CORE_M_SA_YOY",
        derived_series_name="United States CPI Core, YoY",
        derived_series_description="Year-over-year percent growth computed from core CPI levels.",
        derived_family_variant="Core YoY",
    ),
)


async def run_fred_us_macro_bootstrap(
    *,
    database: DatabaseTarget = DatabaseTarget.APP,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
    client: FredClientProtocol | None = None,
    run_date: date | None = None,
) -> FredUsMacroBootstrapResult:
    """Run the curated FRED U.S. macro bootstrap against the selected database."""

    resolved_run_date = run_date or date.today()
    code_version = _current_code_version()
    managed_engine = None

    if session_factory is None:
        managed_engine = create_async_engine_for_url(database_url_for_target(database))
        session_factory = create_session_factory(managed_engine)

    try:
        return await _run_bootstrap_transaction(
            session_factory=session_factory,
            client=client,
            database=database,
            run_date=resolved_run_date,
            code_version=code_version,
        )
    finally:
        if managed_engine is not None:
            await managed_engine.dispose()


async def reset_fred_us_macro_bootstrap(
    *,
    database: DatabaseTarget = DatabaseTarget.APP,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
) -> FredUsMacroResetResult:
    """Delete the curated first-pass FRED preset rows while preserving provider seeds."""

    managed_engine = None
    if session_factory is None:
        managed_engine = create_async_engine_for_url(database_url_for_target(database))
        session_factory = create_session_factory(managed_engine)

    try:
        async with session_factory() as session:
            try:
                result = await _reset_bootstrap_transaction(session, database=database)
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
    database: DatabaseTarget,
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
                prepared_derived_series: list[PreparedDerivedSeries] = []
                for spec in RAW_SERIES_SPECS:
                    prepared = await _prepare_series_catalog(
                        session,
                        spec=spec,
                        geography=usa,
                        provider_catalog=catalog,
                    )
                    prepared_raw_series.append(prepared[0])
                    prepared_derived_series.append(prepared[1])

                raw_results: list[FredImportOutcome] = []
                for prepared in prepared_raw_series:
                    outcome = await import_fred_latest_snapshot(
                        session,
                        client=runtime_client,
                        series_id=prepared.series.id,
                        series_code=prepared.series.code,
                        frequency=prepared.spec.frequency,
                        external_code=prepared.spec.external_code,
                        ingestion_feed=prepared.feed,
                        ingestion_feed_member=prepared.feed_member,
                        series_source=prepared.source,
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

                derived_results: list[DerivedComputationOutcome] = []
                for prepared in prepared_derived_series:
                    derived_results.append(
                        await _compute_and_write_yoy_series(
                            session,
                            prepared=prepared,
                            run_date=run_date,
                            code_version=code_version,
                        ),
                    )
            finally:
                if owned_client is not None:
                    await owned_client.aclose()

            await session.commit()
            return FredUsMacroBootstrapResult(
                database=database,
                run_date=run_date,
                raw_imports=tuple(raw_results),
                derived_imports=tuple(derived_results),
            )
        except Exception:
            await session.rollback()
            raise


async def _reset_bootstrap_transaction(
    session: AsyncSession,
    *,
    database: DatabaseTarget,
) -> FredUsMacroResetResult:
    series_codes = _all_bootstrap_series_codes()
    series_rows = (
        await session.execute(
            select(Series.id, Series.code).where(Series.code.in_(series_codes)),
        )
    ).all()
    if not series_rows:
        return FredUsMacroResetResult(
            database=database,
            observations_deleted=0,
            ingestion_run_logs_deleted=0,
            computation_run_logs_deleted=0,
            derivation_inputs_deleted=0,
            derived_series_deleted=0,
            ingestion_feeds_deleted=0,
            series_sources_deleted=0,
            family_members_deleted=0,
            series_deleted=0,
            families_deleted=0,
            concepts_deleted=0,
        )

    series_ids = {series_id for series_id, _ in series_rows}
    raw_codes = {spec.series_code for spec in RAW_SERIES_SPECS}
    raw_series_ids = {series_id for series_id, code in series_rows if code in raw_codes}
    derived_output_ids = series_ids - raw_series_ids

    source_ids = set(
        (
            await session.execute(
                select(SeriesSource.id).where(SeriesSource.series_id.in_(raw_series_ids)),
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
    derived_series_ids = set(
        (
            await session.execute(
                select(DerivedSeries.id).where(DerivedSeries.series_id.in_(derived_output_ids)),
            )
        ).scalars().all()
    )

    observations_deleted = await _execute_delete(
        session,
        delete(Observation).where(Observation.series_id.in_(series_ids)),
    )
    computation_run_logs_deleted = await _execute_delete(
        session,
        delete(ComputationRunLog).where(ComputationRunLog.derived_series_id.in_(derived_series_ids)),
    )
    await _execute_delete(
        session,
        delete(IngestionRunLogMember).where(IngestionRunLogMember.ingestion_run_log_id.in_(ingestion_run_log_ids)),
    )
    ingestion_run_logs_deleted = await _execute_delete(
        session,
        delete(IngestionRunLog).where(IngestionRunLog.ingestion_feed_id.in_(feed_ids)),
    )
    derivation_inputs_deleted = await _execute_delete(
        session,
        delete(DerivationInput).where(DerivationInput.derived_series_id.in_(derived_series_ids)),
    )
    derived_series_deleted = await _execute_delete(
        session,
        delete(DerivedSeries).where(DerivedSeries.id.in_(derived_series_ids)),
    )
    ingestion_feeds_deleted = await _execute_delete(
        session,
        delete(IngestionFeed).where(IngestionFeed.id.in_(feed_ids)),
    )
    series_sources_deleted = await _execute_delete(
        session,
        delete(SeriesSource).where(SeriesSource.id.in_(source_ids)),
    )
    family_members_deleted = await _execute_delete(
        session,
        delete(SeriesFamilyMember).where(SeriesFamilyMember.series_id.in_(series_ids)),
    )
    series_deleted = await _execute_delete(
        session,
        delete(Series).where(Series.id.in_(series_ids)),
    )

    families_deleted = 0
    for family_code in _bootstrap_family_codes():
        family = await session.scalar(select(SeriesFamily).where(SeriesFamily.code == family_code))
        if family is None:
            continue
        has_members = await session.scalar(
            select(SeriesFamilyMember.series_id).where(SeriesFamilyMember.family_id == family.id).limit(1),
        )
        if has_members is None:
            families_deleted += await _execute_delete(
                session,
                delete(SeriesFamily).where(SeriesFamily.id == family.id),
            )

    concepts_deleted = 0
    for concept_code in _bootstrap_concept_codes():
        concept = await session.scalar(select(Concept).where(Concept.code == concept_code))
        if concept is None:
            continue
        has_families = await session.scalar(
            select(SeriesFamily.id).where(SeriesFamily.concept_id == concept.id).limit(1),
        )
        if has_families is None:
            concepts_deleted += await _execute_delete(
                session,
                delete(Concept).where(Concept.id == concept.id),
            )

    return FredUsMacroResetResult(
        database=database,
        observations_deleted=observations_deleted,
        ingestion_run_logs_deleted=ingestion_run_logs_deleted,
        computation_run_logs_deleted=computation_run_logs_deleted,
        derivation_inputs_deleted=derivation_inputs_deleted,
        derived_series_deleted=derived_series_deleted,
        ingestion_feeds_deleted=ingestion_feeds_deleted,
        series_sources_deleted=series_sources_deleted,
        family_members_deleted=family_members_deleted,
        series_deleted=series_deleted,
        families_deleted=families_deleted,
        concepts_deleted=concepts_deleted,
    )


def compute_yoy_growth(*, current: Decimal, prior: Decimal) -> Decimal:
    """Compute a year-over-year percent change from level inputs."""

    return ((current / prior) - Decimal("1")) * Decimal("100")


async def _prepare_series_catalog(
    session: AsyncSession,
    *,
    spec: RawSeriesSpec,
    geography: Geography,
    provider_catalog: ProviderCatalog,
) -> tuple[PreparedRawSeries, PreparedDerivedSeries]:
    concept = await _upsert_concept(
        session,
        payload=ConceptCreate(
            code=spec.concept_code,
            name=spec.concept_name,
            description=spec.concept_description,
        ).model_dump(),
    )
    family = await _upsert_series_family(
        session,
        payload=SeriesFamilyCreate(
            code=spec.family_code,
            name=spec.family_name,
            description=spec.family_description,
            concept_id=concept.id,
            geography_id=geography.id,
        ).model_dump(),
    )

    raw_series = await _upsert_series(
        session,
        payload=_raw_series_payload(spec, geography_id=geography.id),
    )
    await _upsert_series_family_member(
        session,
        payload=SeriesFamilyMemberCreate(
            family_id=family.id,
            series_id=raw_series.id,
            variant=spec.family_variant,
            is_primary=spec.is_primary_family_member,
        ).model_dump(),
    )
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
            selector_type="fred_series_id",
            selector_config={"series_id": spec.external_code},
            is_active=True,
        ).model_dump(),
    )

    derived_output_series = await _upsert_series(
        session,
        payload=_derived_series_payload(spec, geography_id=geography.id),
    )
    await _upsert_series_family_member(
        session,
        payload=SeriesFamilyMemberCreate(
            family_id=family.id,
            series_id=derived_output_series.id,
            variant=spec.derived_family_variant,
            is_primary=False,
        ).model_dump(),
    )
    derived_series = await _upsert_derived_series(
        session,
        payload=DerivedSeriesCreate(
            series_id=derived_output_series.id,
            formula_config={
                "op": "yoy_percent_change",
                "lag_periods": _yoy_lag_for_frequency(spec.frequency),
            },
            description=spec.derived_series_description,
            execution_policy=ExecutionPolicy.UPSTREAM_UPDATE,
            is_deterministic=True,
            requires_vintage_awareness=False,
            code_ref=_YOY_CODE_REF,
        ).model_dump(),
    )
    await _upsert_derivation_input(
        session,
        payload=DerivationInputCreate(
            derived_series_id=derived_series.id,
            input_series_id=raw_series.id,
            notes="single-input year-over-year growth",
        ).model_dump(),
    )

    return (
        PreparedRawSeries(spec=spec, series=raw_series, source=source, feed=feed, feed_member=feed_member),
        PreparedDerivedSeries(
            spec=spec,
            output_series=derived_output_series,
            derived_series=derived_series,
            input_series=raw_series,
        ),
    )


async def _compute_and_write_yoy_series(
    session: AsyncSession,
    *,
    prepared: PreparedDerivedSeries,
    run_date: date,
    code_version: str | None,
) -> DerivedComputationOutcome:
    started_at = datetime.now(timezone.utc)
    latest_input_observations = await _load_latest_series_observations(
        session,
        series_id=prepared.input_series.id,
    )
    latest_output_by_period = await _load_latest_observations_by_period_for_series(
        session,
        series_id=prepared.output_series.id,
    )

    rows_to_write: list[dict[str, Any]] = []
    rows_computed = 0
    rows_skipped = 0
    for current_observation in latest_input_observations.values():
        prior_period_start = _prior_year_period_start(
            current_observation.period_start,
            frequency=prepared.spec.frequency,
        )
        prior_observation = latest_input_observations.get(prior_period_start)
        if (
            prior_observation is None
            or current_observation.value is None
            or prior_observation.value is None
            or prior_observation.value == 0
        ):
            rows_skipped += 1
            continue

        rows_computed += 1
        output_value = compute_yoy_growth(
            current=current_observation.value,
            prior=prior_observation.value,
        )
        existing = latest_output_by_period.get(current_observation.period_start)
        if existing is not None and existing.value == output_value:
            rows_skipped += 1
            continue

        rows_to_write.append(
            {
                "series_id": prepared.output_series.id,
                "period_start": current_observation.period_start,
                "period_end": current_observation.period_end,
                "value": output_value,
                "vintage_date": run_date,
            },
        )

    run_log = ComputationRunLog(
        derived_series_id=prepared.derived_series.id,
        started_at=started_at,
        finished_at=datetime.now(timezone.utc),
        status=ComputationRunStatus.SUCCESS,
        rows_computed=rows_computed,
        rows_inserted=len(rows_to_write),
        rows_updated=0,
        rows_skipped=rows_skipped,
        triggered_by=ComputationTriggeredBy.UPSTREAM_UPDATE,
        code_version=code_version,
        input_vintage_policy=InputVintagePolicy.LATEST_AVAILABLE,
        parameters={
            "input_series_code": prepared.input_series.code,
            "snapshot_vintage_date": run_date.isoformat(),
        },
        output_mode=OutputMode.WRITE_OBSERVATIONS,
        notes="latest-snapshot YoY computation",
    )
    session.add(run_log)
    await session.flush()

    if rows_to_write:
        for row in rows_to_write:
            row["computation_run_log_id"] = run_log.id

        statement = insert(Observation).values(rows_to_write)
        excluded = statement.excluded
        statement = statement.on_conflict_do_update(
            index_elements=[
                Observation.series_id,
                Observation.period_start,
                Observation.vintage_date,
            ],
            set_={
                "period_end": excluded.period_end,
                "value": excluded.value,
                "ingestion_run_log_member_id": None,
                "computation_run_log_id": excluded.computation_run_log_id,
            },
        )
        await session.execute(statement)

        derived_start_date = min(row["period_start"] for row in rows_to_write)
        if prepared.output_series.start_date is None or prepared.output_series.start_date > derived_start_date:
            prepared.output_series.start_date = derived_start_date

    return DerivedComputationOutcome(
        series_code=prepared.output_series.code,
        rows_computed=rows_computed,
        rows_written=len(rows_to_write),
        rows_skipped=rows_skipped,
    )


async def _load_latest_series_observations(
    session: AsyncSession,
    *,
    series_id: Any,
) -> dict[date, Observation]:
    rows = (
        await session.execute(
            select(Observation)
            .where(Observation.series_id == series_id)
            .order_by(Observation.period_start, Observation.vintage_date.desc()),
        )
    ).scalars()

    latest: dict[date, Observation] = {}
    for row in rows:
        latest.setdefault(row.period_start, row)
    return latest


async def _load_latest_observations_by_period_for_series(
    session: AsyncSession,
    *,
    series_id: Any,
) -> dict[date, Observation]:
    return await _load_latest_series_observations(session, series_id=series_id)


def _prior_year_period_start(period_start: date, *, frequency: Frequency) -> date:
    if frequency is Frequency.MONTHLY:
        return date(period_start.year - 1, period_start.month, 1)
    if frequency is Frequency.QUARTERLY:
        return date(period_start.year - 1, period_start.month, 1)
    if frequency is Frequency.ANNUAL:
        return date(period_start.year - 1, 1, 1)
    raise ValueError(f"YoY computation is not implemented for frequency {frequency.value!r}")


def _yoy_lag_for_frequency(frequency: Frequency) -> int:
    if frequency is Frequency.MONTHLY:
        return 12
    if frequency is Frequency.QUARTERLY:
        return 4
    if frequency is Frequency.ANNUAL:
        return 1
    raise ValueError(f"YoY lag is not implemented for frequency {frequency.value!r}")


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


async def _upsert_concept(session: AsyncSession, *, payload: dict[str, Any]) -> Concept:
    concept = await session.scalar(select(Concept).where(Concept.code == payload["code"]))
    if concept is None:
        concept = Concept(**payload)
        session.add(concept)
        await session.flush()
        return concept
    assign_if_changed(concept, payload, ("name", "description"))
    await session.flush()
    return concept


async def _upsert_series_family(
    session: AsyncSession,
    *,
    payload: dict[str, Any],
) -> SeriesFamily:
    family = await session.scalar(select(SeriesFamily).where(SeriesFamily.code == payload["code"]))
    if family is None:
        family = SeriesFamily(**payload)
        session.add(family)
        await session.flush()
        return family
    assign_if_changed(
        family,
        payload,
        ("name", "description", "concept_id", "geography_id"),
    )
    await session.flush()
    return family


async def _upsert_series(
    session: AsyncSession,
    *,
    payload: dict[str, Any],
) -> Series:
    series = await session.scalar(select(Series).where(Series.code == payload["code"]))
    if series is None:
        series = Series(**payload)
        session.add(series)
        await session.flush()
        return series
    assign_if_changed(
        series,
        payload,
        (
            "name",
            "description",
            "origin_type",
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


async def _upsert_series_family_member(
    session: AsyncSession,
    *,
    payload: dict[str, Any],
) -> SeriesFamilyMember:
    member = await session.scalar(
        select(SeriesFamilyMember).where(SeriesFamilyMember.series_id == payload["series_id"]),
    )
    if member is None:
        member = SeriesFamilyMember(**payload)
        session.add(member)
        await session.flush()
        return member
    assign_if_changed(member, payload, ("family_id", "variant", "is_primary"))
    await session.flush()
    return member


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


async def _upsert_derived_series(
    session: AsyncSession,
    *,
    payload: dict[str, Any],
) -> DerivedSeries:
    derived = await session.scalar(
        select(DerivedSeries).where(DerivedSeries.series_id == payload["series_id"]),
    )
    if derived is None:
        derived = DerivedSeries(**payload)
        session.add(derived)
        await session.flush()
        return derived
    assign_if_changed(
        derived,
        payload,
        (
            "formula_config",
            "description",
            "execution_policy",
            "is_deterministic",
            "requires_vintage_awareness",
            "code_ref",
        ),
    )
    await session.flush()
    return derived


async def _upsert_derivation_input(
    session: AsyncSession,
    *,
    payload: dict[str, Any],
) -> DerivationInput:
    derivation_input = await session.scalar(
        select(DerivationInput).where(
            DerivationInput.derived_series_id == payload["derived_series_id"],
            DerivationInput.input_series_id == payload["input_series_id"],
        ),
    )
    if derivation_input is None:
        derivation_input = DerivationInput(**payload)
        session.add(derivation_input)
        await session.flush()
        return derivation_input
    assign_if_changed(derivation_input, payload, ("notes",))
    await session.flush()
    return derivation_input


def _raw_series_payload(spec: RawSeriesSpec, *, geography_id: Any) -> dict[str, Any]:
    return SeriesCreate(
        code=spec.series_code,
        name=spec.series_name,
        description=spec.series_description,
        origin_type=OriginType.INGESTED,
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


def _derived_series_payload(spec: RawSeriesSpec, *, geography_id: Any) -> dict[str, Any]:
    return SeriesCreate(
        code=spec.derived_series_code,
        name=spec.derived_series_name,
        description=spec.derived_series_description,
        origin_type=OriginType.DERIVED,
        geography_id=geography_id,
        frequency=spec.frequency,
        temporal_stock_flow=TemporalStockFlow.RATE,
        unit_kind=UnitKind.PERCENT,
        unit_scale=UnitScale.ONE,
        unit_label=None,
        price_basis=spec.price_basis,
        currency_code=None,
        measure=Measure.GROWTH,
        measure_horizon=MeasureHorizon.YOY,
        annualized=False,
        seasonal_adjustment=spec.seasonal_adjustment,
        reference_kind=None,
        reference_year=None,
        reference_label=None,
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
    return tuple(
        code
        for spec in RAW_SERIES_SPECS
        for code in (spec.series_code, spec.derived_series_code)
    )


def _bootstrap_family_codes() -> tuple[str, ...]:
    return tuple(dict.fromkeys(spec.family_code for spec in RAW_SERIES_SPECS))


def _bootstrap_concept_codes() -> tuple[str, ...]:
    return tuple(dict.fromkeys(spec.concept_code for spec in RAW_SERIES_SPECS))


async def _execute_delete(session: AsyncSession, statement: Any) -> int:
    result = await session.execute(statement)
    return int(result.rowcount or 0)


__all__ = [
    "DatabaseTarget",
    "DerivedComputationOutcome",
    "FredUsMacroBootstrapResult",
    "FredUsMacroResetResult",
    "compute_yoy_growth",
    "reset_fred_us_macro_bootstrap",
    "run_fred_us_macro_bootstrap",
]
