"""Integration coverage for embed-on-write registration helpers.

The concept/indicator registration helpers were dropped with the V7 spine
(ADR 0025); `register_series` is the remaining embed-on-write chokepoint, so the
transactional-semantics coverage now rides on it.
"""

from __future__ import annotations

import asyncio

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

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
from macro_foundry.schemas import SeriesCreate
from macro_foundry.services.embeddings import EMBEDDING_DIMENSIONS, EMBEDDING_MODEL, hash_embedding_input
from macro_foundry.services.registration import register_series


def _series_payload(*, geography_id, code: str) -> SeriesCreate:
    return SeriesCreate(
        code=code,
        name=f"{code} name",
        origin_type=OriginType.INGESTED,
        geography_id=geography_id,
        frequency=Frequency.MONTHLY,
        temporal_stock_flow=TemporalStockFlow.STOCK,
        unit_kind=UnitKind.INDEX,
        unit_scale=UnitScale.ONE,
        measure=Measure.LEVEL,
        annualized=False,
        seasonal_adjustment=SeasonalAdjustment.NSA,
        is_active=True,
    )


async def _usa_geography_id(session: AsyncSession):
    geography = await session.scalar(select(Geography).where(Geography.code == "USA"))
    assert geography is not None
    return geography.id


@pytest.mark.asyncio
async def test_register_series_populates_embedding_fields_from_series_payload(
    session: AsyncSession,
) -> None:
    geography = await session.scalar(select(Geography).where(Geography.code == "USA"))
    assert geography is not None

    expected_text = "\n".join(
        [
            "Type: Series",
            "Code: TEST_SERIES",
            "Name: Test series",
            "Alt names: Alias one, Alias two",
            "Description: Test series description",
            "Geography: United States",
            "Frequency: monthly",
            "Unit: index",
            "Unit label: index",
            "Measure: level",
            "Seasonal adjustment: not seasonally adjusted",
        ],
    )
    vector = [0.75] * EMBEDDING_DIMENSIONS

    monkeypatch = pytest.MonkeyPatch()

    async def fake_embed_text(text: str) -> list[float]:
        assert text == expected_text
        return vector

    monkeypatch.setattr(
        "macro_foundry.services.registration.embed_text",
        fake_embed_text,
    )
    try:
        series = await register_series(
            session,
            SeriesCreate(
                code="TEST_SERIES",
                name="Test series",
                alt_name=["Alias one", "Alias two"],
                description="Test series description",
                origin_type=OriginType.INGESTED,
                geography_id=geography.id,
                frequency=Frequency.MONTHLY,
                temporal_stock_flow=TemporalStockFlow.STOCK,
                unit_kind=UnitKind.INDEX,
                unit_scale=UnitScale.ONE,
                unit_label="index",
                measure=Measure.LEVEL,
                annualized=False,
                seasonal_adjustment=SeasonalAdjustment.NSA,
                is_active=True,
            ),
        )

        assert series.id is not None
        assert series.embedding == vector
        assert series.embedding_model == EMBEDDING_MODEL
        assert series.embedding_input_hash == hash_embedding_input(expected_text)
    finally:
        monkeypatch.undo()


@pytest.mark.asyncio
async def test_register_series_leaves_commit_boundary_to_caller(
    test_engine: AsyncEngine,
) -> None:
    session_factory = async_sessionmaker(
        bind=test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )
    vector = [0.9] * EMBEDDING_DIMENSIONS

    monkeypatch = pytest.MonkeyPatch()

    async def fake_embed_text(_: str) -> list[float]:
        return vector

    monkeypatch.setattr(
        "macro_foundry.services.registration.embed_text",
        fake_embed_text,
    )
    try:
        async with session_factory() as writer:
            geography_id = await _usa_geography_id(writer)
            await register_series(writer, _series_payload(geography_id=geography_id, code="TEST_NO_COMMIT_SERIES"))

            async with session_factory() as reader:
                before_commit = await reader.scalar(
                    select(Series).where(Series.code == "TEST_NO_COMMIT_SERIES"),
                )
                assert before_commit is None

            await writer.commit()

        async with session_factory() as reader:
            after_commit = await reader.scalar(
                select(Series).where(Series.code == "TEST_NO_COMMIT_SERIES"),
            )
            assert after_commit is not None
            await reader.delete(after_commit)
            await reader.commit()
    finally:
        monkeypatch.undo()


@pytest.mark.asyncio
async def test_register_series_embed_failure_leaves_no_partial_write(
    test_engine: AsyncEngine,
) -> None:
    session_factory = async_sessionmaker(
        bind=test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )

    monkeypatch = pytest.MonkeyPatch()

    async def fake_embed_text(_: str) -> list[float]:
        raise RuntimeError("embedding unavailable")

    monkeypatch.setattr(
        "macro_foundry.services.registration.embed_text",
        fake_embed_text,
    )
    try:
        async with session_factory() as writer:
            geography_id = await _usa_geography_id(writer)
            with pytest.raises(RuntimeError, match="embedding unavailable"):
                await register_series(writer, _series_payload(geography_id=geography_id, code="TEST_EMBED_FAIL_SERIES"))

            assert list(writer.new) == []
            await writer.rollback()

        async with session_factory() as reader:
            persisted = await reader.scalar(
                select(Series).where(Series.code == "TEST_EMBED_FAIL_SERIES"),
            )
            assert persisted is None
    finally:
        monkeypatch.undo()


@pytest.mark.asyncio
async def test_register_series_serializes_same_session_concurrent_calls(
    session: AsyncSession,
) -> None:
    geography_id = await _usa_geography_id(session)
    monkeypatch = pytest.MonkeyPatch()

    async def fake_embed_text(text: str) -> list[float]:
        await asyncio.sleep(0.01)
        if "TEST_CONCURRENT_A" in text:
            return [1.0] * EMBEDDING_DIMENSIONS
        return [2.0] * EMBEDDING_DIMENSIONS

    monkeypatch.setattr(
        "macro_foundry.services.registration.embed_text",
        fake_embed_text,
    )
    try:
        series_a, series_b = await asyncio.gather(
            register_series(session, _series_payload(geography_id=geography_id, code="TEST_CONCURRENT_A")),
            register_series(session, _series_payload(geography_id=geography_id, code="TEST_CONCURRENT_B")),
        )

        rows = list(
            (
                await session.execute(
                    select(Series).where(
                        Series.code.in_(["TEST_CONCURRENT_A", "TEST_CONCURRENT_B"]),
                    ),
                )
            ).scalars().all(),
        )

        assert {row.code for row in rows} == {"TEST_CONCURRENT_A", "TEST_CONCURRENT_B"}
        assert series_a.embedding == [1.0] * EMBEDDING_DIMENSIONS
        assert series_b.embedding == [2.0] * EMBEDDING_DIMENSIONS
        assert series_a.embedding_input_hash != series_b.embedding_input_hash
    finally:
        monkeypatch.undo()
