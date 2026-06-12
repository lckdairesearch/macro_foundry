"""Integration coverage for the curated FRED U.S. macro bootstrap."""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from macro_foundry.bootstrap import (
    EnvTarget,
    reset_fred_us_macro_bootstrap,
    run_fred_us_macro_bootstrap,
)
from macro_foundry.enums import Frequency
from macro_foundry.ingestion.providers import FredObservation, FredSeriesMetadata
from macro_foundry.models import (
    ComputationRunLog,
    Concept,
    DerivedSeries,
    IngestionFeed,
    IngestionFeedMember,
    IngestionRunLog,
    IngestionRunLogMember,
    Observation,
    Series,
    SeriesFamily,
    SeriesFamilyMember,
    SeriesSource,
)


class FakeFredClient:
    """Simple in-memory client used to drive bootstrap tests."""

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


def _build_fake_client() -> FakeFredClient:
    metadata_by_series_id = {
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
    }

    observations_by_series_id = {
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
    }

    return FakeFredClient(
        metadata_by_series_id=metadata_by_series_id,
        observations_by_series_id=observations_by_series_id,
    )


async def _count_rows(session: AsyncSession, model: type[object]) -> int:
    return await session.scalar(select(func.count()).select_from(model)) or 0


async def _series(session: AsyncSession, code: str) -> Series:
    series = await session.scalar(select(Series).where(Series.code == code))
    assert series is not None
    return series


@pytest.mark.asyncio
async def test_fred_bootstrap_creates_curated_rows_and_run_logs(
    test_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    client = _build_fake_client()

    summary = await run_fred_us_macro_bootstrap(
        target=EnvTarget.TEST,
        session_factory=test_session_factory,
        client=client,
        run_date=date(2026, 6, 9),
    )

    assert summary.target is EnvTarget.TEST
    assert len(summary.raw_imports) == 4
    assert len(summary.derived_imports) == 4
    assert sum(result.rows_written for result in summary.raw_imports) == 18
    assert sum(result.rows_written for result in summary.derived_imports) == 8

    async with test_session_factory() as session:
        assert await _count_rows(session, Concept) == 2
        assert await _count_rows(session, SeriesFamily) == 2
        assert await _count_rows(session, Series) == 8
        assert await _count_rows(session, SeriesFamilyMember) == 8
        assert await _count_rows(session, SeriesSource) == 4
        assert await _count_rows(session, IngestionFeed) == 4
        assert await _count_rows(session, IngestionFeedMember) == 4
        assert await _count_rows(session, DerivedSeries) == 4
        assert await _count_rows(session, IngestionRunLog) == 4
        assert await _count_rows(session, IngestionRunLogMember) == 4
        assert await _count_rows(session, ComputationRunLog) == 4
        assert await _count_rows(session, Observation) == 26

        raw_series = await _series(session, "US_CPI_HEADLINE_M_NSA_LEVEL")
        derived_series = await _series(session, "US_CPI_HEADLINE_M_NSA_YOY")
        assert raw_series.start_date == date(2025, 1, 1)
        assert derived_series.start_date == date(2026, 1, 1)

        source = await session.scalar(
            select(SeriesSource).where(SeriesSource.external_code == "GDP"),
        )
        assert source is not None
        assert source.external_name == "Gross Domestic Product"
        assert source.provider_catalog.provider.credentials_ref == "FRED_API_KEY"
        assert source.provider_catalog.provider.base_url == "https://api.stlouisfed.org/fred"

        feed_member = await session.scalar(
            select(IngestionFeedMember).where(IngestionFeedMember.series_source_id == source.id),
        )
        assert feed_member is not None
        assert feed_member.selector_type == "json_path"
        assert feed_member.selector_config == {
            "series_id": "GDP",
            "metadata_endpoint": "/series",
            "observations_endpoint": "/series/observations",
            "records_path": "observations",
            "period_anchor_field": "date",
            "value_field": "value",
            "missing_value_tokens": [".", ""],
            "frequency": Frequency.QUARTERLY.value,
            "frequency_map": {
                "A": Frequency.ANNUAL.value,
                "D": Frequency.DAILY.value,
                "M": Frequency.MONTHLY.value,
                "Q": Frequency.QUARTERLY.value,
                "SA": Frequency.SEMI_ANNUAL.value,
                "W": Frequency.WEEKLY.value,
            },
        }
        feed = await session.get(IngestionFeed, feed_member.ingestion_feed_id)
        assert feed is not None
        assert feed.cron_schedule == "TZ=America/New_York 0 8 * * *"
        assert feed.endpoint_url == "/series/observations"
        assert feed.request_params is None
        member_log = await session.scalar(
            select(IngestionRunLogMember).where(IngestionRunLogMember.ingestion_feed_member_id == feed_member.id),
        )
        assert member_log is not None
        assert member_log.rows_inserted == 4
        assert member_log.diagnostics == {"selector_type": "json_path", "outcome": "data"}
        gdp_observations = (
            await session.execute(
                select(Observation)
                .where(Observation.series_id == source.series_id)
                .order_by(Observation.period_start),
            )
        ).scalars().all()
        assert len(gdp_observations) == 4
        assert {row.ingestion_run_log_member_id for row in gdp_observations} == {member_log.id}

    assert client.metadata_endpoints["GDP"] == ["/series"]
    assert client.observation_endpoints["GDP"] == ["/series/observations"]


@pytest.mark.asyncio
async def test_fred_bootstrap_rerun_skips_unchanged_snapshot_rows(
    test_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    client = _build_fake_client()

    await run_fred_us_macro_bootstrap(
        target=EnvTarget.TEST,
        session_factory=test_session_factory,
        client=client,
        run_date=date(2026, 6, 9),
    )
    second_summary = await run_fred_us_macro_bootstrap(
        target=EnvTarget.TEST,
        session_factory=test_session_factory,
        client=client,
        run_date=date(2026, 6, 10),
    )

    assert all(result.rows_written == 0 for result in second_summary.raw_imports)
    assert all(result.rows_written == 0 for result in second_summary.derived_imports)
    assert all(result.rows_skipped > 0 for result in second_summary.raw_imports)
    assert client.observation_starts["GDP"] == [None, date(2024, 4, 1)]
    assert client.observation_starts["CPIAUCNS"] == [None, date(2024, 8, 1)]

    async with test_session_factory() as session:
        assert await _count_rows(session, Observation) == 26
        assert await _count_rows(session, IngestionRunLog) == 8
        assert await _count_rows(session, IngestionRunLogMember) == 8
        assert await _count_rows(session, ComputationRunLog) == 8
        zero_write_member_logs = (
            await session.execute(
                select(IngestionRunLogMember).where(IngestionRunLogMember.rows_inserted == 0),
            )
        ).scalars().all()
        assert len(zero_write_member_logs) == 4


@pytest.mark.asyncio
async def test_fred_bootstrap_rerun_inserts_only_changed_and_new_rows(
    test_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    client = _build_fake_client()

    await run_fred_us_macro_bootstrap(
        target=EnvTarget.TEST,
        session_factory=test_session_factory,
        client=client,
        run_date=date(2026, 6, 9),
    )

    client.metadata_by_series_id["CPIAUCNS"] = FredSeriesMetadata(
        series_id="CPIAUCNS",
        title="Consumer Price Index for All Urban Consumers: All Items in U.S. City Average",
        frequency=Frequency.MONTHLY,
        observation_start=date(2025, 1, 1),
        observation_end=date(2026, 3, 1),
    )
    client.observations_by_series_id["CPIAUCNS"] = [
        FredObservation(period_anchor=date(2025, 1, 1), value=Decimal("100")),
        FredObservation(period_anchor=date(2025, 2, 1), value=Decimal("101")),
        FredObservation(period_anchor=date(2025, 3, 1), value=Decimal("102")),
        FredObservation(period_anchor=date(2026, 1, 1), value=Decimal("103")),
        FredObservation(period_anchor=date(2026, 2, 1), value=Decimal("105")),
        FredObservation(period_anchor=date(2026, 3, 1), value=Decimal("106")),
    ]

    summary = await run_fred_us_macro_bootstrap(
        target=EnvTarget.TEST,
        session_factory=test_session_factory,
        client=client,
        run_date=date(2026, 6, 10),
    )

    raw_result = next(
        result
        for result in summary.raw_imports
        if result.series_code == "US_CPI_HEADLINE_M_NSA_LEVEL"
    )
    derived_result = next(
        result
        for result in summary.derived_imports
        if result.series_code == "US_CPI_HEADLINE_M_NSA_YOY"
    )
    assert raw_result.rows_written == 2
    assert derived_result.rows_written == 2

    async with test_session_factory() as session:
        raw_series = await _series(session, "US_CPI_HEADLINE_M_NSA_LEVEL")
        derived_series = await _series(session, "US_CPI_HEADLINE_M_NSA_YOY")

        raw_rows = (
            await session.execute(
                select(Observation)
                .where(
                    Observation.series_id == raw_series.id,
                    Observation.vintage_date == date(2026, 6, 10),
                )
                .order_by(Observation.period_start),
            )
        ).scalars().all()
        assert [row.period_start for row in raw_rows] == [
            date(2026, 2, 1),
            date(2026, 3, 1),
        ]

        derived_rows = (
            await session.execute(
                select(Observation)
                .where(
                    Observation.series_id == derived_series.id,
                    Observation.vintage_date == date(2026, 6, 10),
                )
                .order_by(Observation.period_start),
            )
        ).scalars().all()
        assert [row.period_start for row in derived_rows] == [
            date(2026, 2, 1),
            date(2026, 3, 1),
        ]


@pytest.mark.asyncio
async def test_fred_bootstrap_reset_removes_curated_preset_rows_only(
    test_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    client = _build_fake_client()

    await run_fred_us_macro_bootstrap(
        target=EnvTarget.TEST,
        session_factory=test_session_factory,
        client=client,
        run_date=date(2026, 6, 9),
    )

    reset_summary = await reset_fred_us_macro_bootstrap(
        target=EnvTarget.TEST,
        session_factory=test_session_factory,
    )

    assert reset_summary.observations_deleted == 26
    assert reset_summary.series_deleted == 8

    async with test_session_factory() as session:
        assert await _count_rows(session, Observation) == 0
        assert await _count_rows(session, IngestionRunLog) == 0
        assert await _count_rows(session, IngestionRunLogMember) == 0
        assert await _count_rows(session, ComputationRunLog) == 0
        assert await _count_rows(session, IngestionFeed) == 0
        assert await _count_rows(session, SeriesSource) == 0
        assert await _count_rows(session, Series) == 0
        assert await _count_rows(session, SeriesFamily) == 0
        assert await _count_rows(session, Concept) == 0
