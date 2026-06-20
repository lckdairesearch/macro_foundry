"""Issue #83: the curated FRED U.S. macro bootstrap, re-grained onto the V8 tree.

The bootstrap attaches each curated series to its most-specific `kind=concept`
node (`series.category_id`), minting a concept under the seeded subdomain
skeleton when one does not yet exist (ADR 0025 §3, ADR 0026 §5). The V7
concept/indicator/variant spine is gone.

Runs against the shared session test database (conftest migrates + seeds to head,
so `CONSUMER_PRICES`, `GDP_AND_GROWTH`, `CPI_ALL_ITEMS`, `GDP_NOMINAL`,
`GDP_REAL` are present). A fake FRED client and a mocked `embed_text` keep the
run hermetic. Writes ride the per-test savepoint and roll back.
"""

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
from macro_foundry.enums import CategoryKind, Frequency
from macro_foundry.ingestion.providers import FredObservation, FredSeriesMetadata
from macro_foundry.models import (
    Category,
    CategoryEdge,
    Geography,
    Observation,
    Series,
)
from macro_foundry.services.embeddings import EMBEDDING_DIMENSIONS, EMBEDDING_MODEL


class FakeFredClient:
    """In-memory client driving bootstrap tests without network access."""

    def __init__(
        self,
        *,
        metadata_by_series_id: dict[str, FredSeriesMetadata],
        observations_by_series_id: dict[str, list[FredObservation]],
    ) -> None:
        self.metadata_by_series_id = metadata_by_series_id
        self.observations_by_series_id = observations_by_series_id
        self.observation_starts: dict[str, list[date | None]] = defaultdict(list)

    async def fetch_series_metadata(
        self, series_id: str, *, endpoint_path: str = "/series",
    ) -> FredSeriesMetadata:
        return self.metadata_by_series_id[series_id]

    async def fetch_series_observations(
        self,
        series_id: str,
        *,
        observation_start: date | None = None,
        endpoint_path: str = "/series/observations",
    ) -> list[FredObservation]:
        self.observation_starts[series_id].append(observation_start)
        rows = self.observations_by_series_id[series_id]
        if observation_start is None:
            return list(rows)
        return [row for row in rows if row.period_anchor >= observation_start]


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
        ],
        "GDPC1": [
            FredObservation(period_anchor=date(2025, 1, 1), value=Decimal("22000")),
            FredObservation(period_anchor=date(2025, 4, 1), value=Decimal("22100")),
        ],
        "CPIAUCNS": [
            FredObservation(period_anchor=date(2025, 1, 1), value=Decimal("100")),
            FredObservation(period_anchor=date(2025, 2, 1), value=Decimal("101")),
        ],
        "CPILFESL": [
            FredObservation(period_anchor=date(2025, 1, 1), value=Decimal("110")),
            FredObservation(period_anchor=date(2025, 2, 1), value=Decimal("111")),
        ],
    }
    return FakeFredClient(
        metadata_by_series_id=metadata_by_series_id,
        observations_by_series_id=observations_by_series_id,
    )


@pytest.fixture(autouse=True)
def _mock_registration_embed_text(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_embed_text(text: str) -> list[float]:
        fill = float((sum(ord(ch) for ch in text) % 13) + 1)
        return [fill] * EMBEDDING_DIMENSIONS

    monkeypatch.setattr("macro_foundry.services.registration.embed_text", fake_embed_text)


async def _count(session: AsyncSession, model: type[object]) -> int:
    return await session.scalar(select(func.count()).select_from(model)) or 0


async def _series(session: AsyncSession, code: str) -> Series:
    series = await session.scalar(select(Series).where(Series.code == code))
    assert series is not None, f"series {code} missing"
    return series


async def _category(session: AsyncSession, code: str) -> Category:
    category = await session.scalar(select(Category).where(Category.code == code))
    assert category is not None, f"category {code} missing"
    return category


@pytest.mark.asyncio
async def test_bootstrap_attaches_series_to_concept_nodes(
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

    async with test_session_factory() as session:
        assert await _count(session, Series) == 4

        # Every bootstrapped series points at a kind=concept node.
        series_rows = (
            await session.execute(
                select(Series).where(Series.code.like("US\\_%", escape="\\")),
            )
        ).scalars().all()
        for row in series_rows:
            assert row.category_id is not None
            concept = await session.get(Category, row.category_id)
            assert concept is not None
            assert concept.kind is CategoryKind.CONCEPT

        # The specific attachments (function-named concepts, not US labels).
        cpi_all = await _category(session, "CPI_ALL_ITEMS")
        cpi_core = await _category(session, "CPI_CORE")
        gdp_nominal = await _category(session, "GDP_NOMINAL")
        gdp_real = await _category(session, "GDP_REAL")

        assert (await _series(session, "US_CPI_HEADLINE_M_NSA")).category_id == cpi_all.id
        assert (await _series(session, "US_CPI_CORE_M_SA")).category_id == cpi_core.id
        assert (await _series(session, "US_GDP_NOMINAL_Q_SAAR")).category_id == gdp_nominal.id
        assert (await _series(session, "US_GDP_REAL_Q_SAAR")).category_id == gdp_real.id


@pytest.mark.asyncio
async def test_bootstrap_accretes_missing_concept_under_seeded_subdomain(
    test_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    client = _build_fake_client()

    async with test_session_factory() as session:
        # CPI_CORE is NOT seeded; CPI_ALL_ITEMS is.
        assert await session.scalar(select(Category).where(Category.code == "CPI_CORE")) is None

    await run_fred_us_macro_bootstrap(
        target=EnvTarget.TEST,
        session_factory=test_session_factory,
        client=client,
        run_date=date(2026, 6, 9),
    )

    async with test_session_factory() as session:
        cpi_core = await _category(session, "CPI_CORE")
        assert cpi_core.kind is CategoryKind.CONCEPT
        # Carries an embedding (ADR 0025 §1).
        assert cpi_core.embedding is not None
        assert cpi_core.embedding_model == EMBEDDING_MODEL

        # Accreted directly under the seeded CONSUMER_PRICES subdomain.
        consumer_prices = await _category(session, "CONSUMER_PRICES")
        edge = await session.scalar(
            select(CategoryEdge).where(CategoryEdge.child_category_id == cpi_core.id),
        )
        assert edge is not None
        assert edge.parent_category_id == consumer_prices.id


@pytest.mark.asyncio
async def test_worked_example_cpi_all_items_usa_resolves(
    test_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """ADR 0025 worked example: series WHERE category=CPI_ALL_ITEMS AND geography=USA."""
    client = _build_fake_client()

    await run_fred_us_macro_bootstrap(
        target=EnvTarget.TEST,
        session_factory=test_session_factory,
        client=client,
        run_date=date(2026, 6, 9),
    )

    async with test_session_factory() as session:
        cpi_all = await _category(session, "CPI_ALL_ITEMS")
        usa = await session.scalar(select(Geography).where(Geography.code == "USA"))
        rows = (
            await session.execute(
                select(Series).where(
                    Series.category_id == cpi_all.id,
                    Series.geography_id == usa.id,
                ),
            )
        ).scalars().all()
        assert [row.code for row in rows] == ["US_CPI_HEADLINE_M_NSA"]


@pytest.mark.asyncio
async def test_bootstrap_is_idempotent(
    test_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    client = _build_fake_client()

    for _ in range(2):
        await run_fred_us_macro_bootstrap(
            target=EnvTarget.TEST,
            session_factory=test_session_factory,
            client=client,
            run_date=date(2026, 6, 9),
        )

    async with test_session_factory() as session:
        assert await _count(session, Series) == 4
        # CPI_CORE accreted exactly once, with a single parent edge.
        cpi_core = await _category(session, "CPI_CORE")
        edges = (
            await session.execute(
                select(CategoryEdge).where(CategoryEdge.child_category_id == cpi_core.id),
            )
        ).scalars().all()
        assert len(edges) == 1


@pytest.mark.asyncio
async def test_reset_removes_series_but_keeps_taxonomy(
    test_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    client = _build_fake_client()

    await run_fred_us_macro_bootstrap(
        target=EnvTarget.TEST,
        session_factory=test_session_factory,
        client=client,
        run_date=date(2026, 6, 9),
    )

    reset = await reset_fred_us_macro_bootstrap(
        target=EnvTarget.TEST,
        session_factory=test_session_factory,
    )
    assert reset.series_deleted == 4
    assert reset.observations_deleted == 8

    async with test_session_factory() as session:
        assert await _count(session, Series) == 0
        assert await _count(session, Observation) == 0
        # The accreted concept node and the seeded skeleton both survive a reset.
        assert await session.scalar(select(Category).where(Category.code == "CPI_CORE")) is not None
        assert await session.scalar(select(Category).where(Category.code == "CPI_ALL_ITEMS")) is not None


@pytest.mark.asyncio
async def test_reset_then_rebootstrap_is_clean(
    test_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    client = _build_fake_client()

    await run_fred_us_macro_bootstrap(
        target=EnvTarget.TEST, session_factory=test_session_factory, client=client,
        run_date=date(2026, 6, 9),
    )
    await reset_fred_us_macro_bootstrap(target=EnvTarget.TEST, session_factory=test_session_factory)
    summary = await run_fred_us_macro_bootstrap(
        target=EnvTarget.TEST, session_factory=test_session_factory, client=client,
        run_date=date(2026, 6, 10),
    )

    assert len(summary.raw_imports) == 4
    async with test_session_factory() as session:
        assert await _count(session, Series) == 4
