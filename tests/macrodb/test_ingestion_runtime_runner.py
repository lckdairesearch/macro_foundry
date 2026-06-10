"""Integration coverage for the generic ingestion runtime runner."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

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
from macro_foundry.ingestion.runtime.runner import execute_feed
from macro_foundry.ingestion.runtime.types import ExtractionResult, ParsedObservation, ValidationResult
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


class StubSelector:
    name = "stub"
    config_schema: dict[str, Any] = {}

    def __init__(self, observations: list[ParsedObservation]) -> None:
        self.observations = observations

    def validate(self, config: dict[str, Any]) -> ValidationResult:
        return ValidationResult(is_valid=True)

    def extract(self, payload: Any, config: dict[str, Any]) -> ExtractionResult:
        assert payload == {"rows": "shared"}
        assert config == {"series": "one"}
        return ExtractionResult(outcome="data", observations=self.observations)


class ConfiguredStubSelector:
    name = "stub"
    config_schema: dict[str, Any] = {}

    def __init__(self, observations_by_key: dict[str, list[ParsedObservation]]) -> None:
        self.observations_by_key = observations_by_key
        self.seen_configs: list[dict[str, Any]] = []

    def validate(self, config: dict[str, Any]) -> ValidationResult:
        return ValidationResult(is_valid=True)

    def extract(self, payload: Any, config: dict[str, Any]) -> ExtractionResult:
        assert payload == {"rows": "shared"}
        self.seen_configs.append(config)
        return ExtractionResult(
            outcome="data",
            observations=self.observations_by_key[str(config["series"])],
        )


@pytest.mark.asyncio
async def test_execute_feed_writes_feed_and_member_run_logs_for_one_member(
    session: AsyncSession,
) -> None:
    source = await _create_series_source(session, code="RUNTIME_TEST_ONE")
    feed = IngestionFeed(
        feed_method=FeedMethod.API,
        endpoint_url="/runtime/test",
        request_params={"dataset": "one"},
        is_active=True,
    )
    session.add(feed)
    await session.flush()
    member = IngestionFeedMember(
        ingestion_feed_id=feed.id,
        series_source_id=source.id,
        selector_type="stub",
        selector_config={"series": "one"},
        execution_order=1,
        is_active=True,
    )
    session.add(member)
    await session.flush()

    outcome = await execute_feed(
        session,
        feed.id,
        payload={"rows": "shared"},
        selectors={
            "stub": StubSelector(
                [
                    ParsedObservation(
                        date(2026, 1, 1),
                        date(2026, 1, 31),
                        Decimal("100.5"),
                        None,
                    ),
                ],
            ),
        },
        run_date=date(2026, 6, 10),
        triggered_by=IngestionTriggeredBy.MANUAL,
        code_version="test",
    )

    assert outcome.status is IngestionRunStatus.SUCCESS
    assert outcome.rows_fetched == 1
    assert outcome.rows_inserted == 1
    assert outcome.rows_skipped == 0

    run_log = await session.get(IngestionRunLog, outcome.run_log_id)
    assert run_log is not None
    assert run_log.ingestion_feed_id == feed.id
    assert run_log.status is IngestionRunStatus.SUCCESS
    assert run_log.rows_fetched == 1
    assert run_log.rows_inserted == 1
    assert run_log.rows_skipped == 0
    assert run_log.triggered_by is IngestionTriggeredBy.MANUAL
    assert run_log.code_version == "test"

    member_log = await session.scalar(
        select(IngestionRunLogMember).where(
            IngestionRunLogMember.ingestion_run_log_id == run_log.id,
        ),
    )
    assert member_log is not None
    assert member_log.ingestion_feed_member_id == member.id
    assert member_log.status is IngestionRunStatus.SUCCESS
    assert member_log.rows_fetched == 1
    assert member_log.rows_inserted == 1
    assert member_log.rows_skipped == 0
    assert member_log.diagnostics == {"selector_type": "stub", "outcome": "data"}

    observations = (
        await session.execute(
            select(Observation).where(
                Observation.ingestion_run_log_member_id == member_log.id,
            ),
        )
    ).scalars().all()
    assert len(observations) == 1
    assert observations[0].series_id == source.series_id
    assert observations[0].period_start == date(2026, 1, 1)
    assert observations[0].period_end == date(2026, 1, 31)
    assert observations[0].value == Decimal("100.5")
    assert observations[0].vintage_date == date(2026, 6, 10)


@pytest.mark.asyncio
async def test_execute_feed_dispatches_multiple_active_members_against_shared_payload(
    session: AsyncSession,
) -> None:
    first_source = await _create_series_source(session, code="RUNTIME_TEST_MULTI_A")
    second_source = await _create_series_source(session, code="RUNTIME_TEST_MULTI_B")
    feed = IngestionFeed(
        feed_method=FeedMethod.API,
        endpoint_url="/runtime/test-multi",
        request_params={"dataset": "multi"},
        is_active=True,
    )
    session.add(feed)
    await session.flush()
    first_member = IngestionFeedMember(
        ingestion_feed_id=feed.id,
        series_source_id=first_source.id,
        selector_type="stub",
        selector_config={"series": "first"},
        execution_order=2,
        is_active=True,
    )
    second_member = IngestionFeedMember(
        ingestion_feed_id=feed.id,
        series_source_id=second_source.id,
        selector_type="stub",
        selector_config={"series": "second"},
        execution_order=1,
        is_active=True,
    )
    session.add_all([first_member, second_member])
    await session.flush()
    selector = ConfiguredStubSelector(
        {
            "first": [
                ParsedObservation(
                    date(2026, 1, 1),
                    date(2026, 1, 31),
                    Decimal("10"),
                    None,
                ),
            ],
            "second": [
                ParsedObservation(
                    date(2026, 2, 1),
                    date(2026, 2, 28),
                    Decimal("20"),
                    None,
                ),
                ParsedObservation(
                    date(2026, 3, 1),
                    date(2026, 3, 31),
                    Decimal("30"),
                    None,
                ),
            ],
        },
    )

    outcome = await execute_feed(
        session,
        feed.id,
        payload={"rows": "shared"},
        selectors={"stub": selector},
        run_date=date(2026, 6, 10),
    )

    assert outcome.status is IngestionRunStatus.SUCCESS
    assert outcome.rows_fetched == 3
    assert outcome.rows_inserted == 3
    assert selector.seen_configs == [{"series": "second"}, {"series": "first"}]

    run_log = await session.get(IngestionRunLog, outcome.run_log_id)
    assert run_log is not None
    member_logs = (
        await session.execute(
            select(IngestionRunLogMember)
            .where(IngestionRunLogMember.ingestion_run_log_id == run_log.id)
            .order_by(IngestionRunLogMember.created_at),
        )
    ).scalars().all()
    assert len(member_logs) == 2
    assert [member_log.ingestion_feed_member_id for member_log in member_logs] == [
        second_member.id,
        first_member.id,
    ]
    assert [member_log.rows_inserted for member_log in member_logs] == [2, 1]

    observations = (
        await session.execute(
            select(Observation)
            .where(
                Observation.ingestion_run_log_member_id.in_(
                    member_log.id for member_log in member_logs
                ),
            )
            .order_by(Observation.period_start),
        )
    ).scalars().all()
    assert [observation.series_id for observation in observations] == [
        first_source.series_id,
        second_source.series_id,
        second_source.series_id,
    ]


async def _create_series_source(session: AsyncSession, *, code: str) -> SeriesSource:
    geography = await session.scalar(select(Geography).where(Geography.code == "USA"))
    assert geography is not None
    provider = Provider(
        name=f"{code} provider",
        type=ProviderType.INTERNAL,
        is_active=True,
    )
    session.add(provider)
    await session.flush()
    catalog = ProviderCatalog(
        provider_id=provider.id,
        name=f"{code} catalog",
        is_placeholder=True,
    )
    session.add(catalog)
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
    await session.flush()
    source = SeriesSource(
        series_id=series.id,
        provider_catalog_id=catalog.id,
        priority=1,
        provider_role=ProviderRole.INTERNAL,
    )
    session.add(source)
    await session.flush()
    return source
