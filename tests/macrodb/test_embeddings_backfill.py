"""Coverage for `macrodb embeddings backfill`.

Concepts and indicators lost their embeddings with the V7 spine (ADR 0025); the
backfill now scans only canonical `series`.
"""

from __future__ import annotations

from collections.abc import Sequence

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from typer.testing import CliRunner

from macro_foundry.cli import app
from macro_foundry.db import EnvTarget
from macro_foundry.enums import (
    Frequency,
    Measure,
    OriginType,
    SeasonalAdjustment,
    TemporalStockFlow,
    UnitKind,
    UnitScale,
)
from macro_foundry.models import Geography, Series

runner = CliRunner()


@pytest.mark.no_db
def test_embeddings_backfill_cli_rejects_test_target() -> None:
    result = runner.invoke(app, ["embeddings", "backfill", "--target", "test"])

    assert result.exit_code == 2
    assert "embeddings backfill does not support --target test (allowed: dev, staging)" in result.output


@pytest.mark.no_db
def test_embeddings_backfill_cli_fails_fast_without_openai_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("macro_foundry.cli.embeddings._openai_api_key", lambda: None)

    result = runner.invoke(app, ["embeddings", "backfill", "--target", "dev"])

    assert result.exit_code == 2
    assert "OPENAI_API_KEY is required for embeddings backfill" in result.output


@pytest.mark.no_db
def test_embeddings_backfill_cli_prints_summary_and_forwards_batch_size(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called: dict[str, object] = {}

    monkeypatch.setattr("macro_foundry.cli.embeddings._openai_api_key", lambda: "test-key")

    async def fake_run_backfill(
        *,
        target: EnvTarget,
        batch_size: int,
    ) -> dict[str, int]:
        called["target"] = target
        called["batch_size"] = batch_size
        return {"series": 3}

    monkeypatch.setattr(
        "macro_foundry.cli.embeddings.run_embeddings_backfill",
        fake_run_backfill,
    )

    result = runner.invoke(app, ["embeddings", "backfill", "--target", "staging"])

    assert result.exit_code == 0
    assert called == {
        "target": EnvTarget.STAGING,
        "batch_size": 50,
    }
    assert "series: 3 stale -> embedded" in result.output


@pytest.mark.asyncio
async def test_run_embeddings_backfill_repairs_stale_rows_and_is_idempotent(
    test_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    from macro_foundry.cli.embeddings import run_embeddings_backfill_with_session_factory
    from macro_foundry.services.embeddings import EMBEDDING_DIMENSIONS, EMBEDDING_MODEL

    geography_id, series_id = await _seed_stale_series_row(test_session_factory)
    batch_sizes: list[int] = []

    async def fake_embed_batch(texts: Sequence[str]) -> list[list[float]]:
        batch_sizes.append(len(texts))
        return [
            [float(index + 1)] * EMBEDDING_DIMENSIONS
            for index in range(len(texts))
        ]

    first = await run_embeddings_backfill_with_session_factory(
        session_factory=test_session_factory,
        embed_batch=fake_embed_batch,
    )

    assert first == {"series": 1}
    assert batch_sizes == [1]

    async with test_session_factory() as session:
        series = await session.get(Series, series_id)
        assert series is not None
        assert series.embedding is not None
        assert series.embedding_model == EMBEDDING_MODEL

        series.description = "Updated description from SQLAdmin-style edit"
        await session.commit()

    batch_sizes.clear()
    second = await run_embeddings_backfill_with_session_factory(
        session_factory=test_session_factory,
        embed_batch=fake_embed_batch,
    )

    assert second == {"series": 1}
    assert batch_sizes == [1]

    batch_sizes.clear()
    third = await run_embeddings_backfill_with_session_factory(
        session_factory=test_session_factory,
        embed_batch=fake_embed_batch,
    )

    assert third == {"series": 0}
    assert batch_sizes == []

    async with test_session_factory() as session:
        geography = await session.get(Geography, geography_id)
        assert geography is not None


@pytest.mark.asyncio
async def test_run_embeddings_backfill_batches_single_openai_call_per_50_rows(
    test_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    from macro_foundry.cli.embeddings import run_embeddings_backfill_with_session_factory
    from macro_foundry.services.embeddings import EMBEDDING_DIMENSIONS

    await _seed_stale_series(test_session_factory, count=51)
    batch_sizes: list[int] = []

    async def fake_embed_batch(texts: Sequence[str]) -> list[list[float]]:
        batch_sizes.append(len(texts))
        return [[0.25] * EMBEDDING_DIMENSIONS for _ in texts]

    result = await run_embeddings_backfill_with_session_factory(
        session_factory=test_session_factory,
        embed_batch=fake_embed_batch,
    )

    assert result["series"] == 51
    assert batch_sizes == [50, 1]


def _stale_series(geography, *, code: str) -> Series:
    return Series(
        code=code,
        name=f"{code} name",
        description="Still stale",
        origin_type=OriginType.INGESTED,
        geography=geography,
        frequency=Frequency.MONTHLY,
        temporal_stock_flow=TemporalStockFlow.STOCK,
        unit_kind=UnitKind.INDEX,
        unit_scale=UnitScale.ONE,
        unit_label="index",
        measure=Measure.LEVEL,
        annualized=False,
        seasonal_adjustment=SeasonalAdjustment.NSA,
        is_active=True,
    )


async def _seed_stale_series_row(
    session_factory: async_sessionmaker[AsyncSession],
):
    async with session_factory() as session:
        geography = await session.scalar(select(Geography).where(Geography.code == "USA"))
        assert geography is not None
        series = _stale_series(geography, code="EMBED_TEST_SERIES")
        session.add(series)
        await session.commit()
        return geography.id, series.id


async def _seed_stale_series(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    count: int,
) -> None:
    async with session_factory() as session:
        geography = await session.scalar(select(Geography).where(Geography.code == "USA"))
        assert geography is not None
        session.add_all(
            [_stale_series(geography, code=f"EMBED_BATCH_{index}") for index in range(count)],
        )
        await session.commit()
