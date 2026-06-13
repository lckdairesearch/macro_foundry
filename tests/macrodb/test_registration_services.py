"""Integration coverage for embed-on-write registration helpers."""

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
from macro_foundry.models import Concept, Geography
from macro_foundry.schemas import ConceptCreate, SeriesCreate, IndicatorCreate
from macro_foundry.services.embeddings import EMBEDDING_DIMENSIONS, EMBEDDING_MODEL, hash_embedding_input
from macro_foundry.services.registration import register_concept, register_indicator, register_series


@pytest.mark.asyncio
async def test_register_concept_populates_embedding_fields_without_committing(
    session: AsyncSession,
) -> None:
    vector = [0.25] * EMBEDDING_DIMENSIONS

    async def fake_embed_text(text: str) -> list[float]:
        assert text == "\n".join(
            [
                "Type: Concept",
                "Code: TEST_CONCEPT",
                "Name: Test concept",
                "Description: Test concept description",
            ],
        )
        return vector

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(
        "macro_foundry.services.registration.embed_text",
        fake_embed_text,
    )
    try:
        concept = await register_concept(
            session,
            ConceptCreate(
                code="TEST_CONCEPT",
                name="Test concept",
                description="Test concept description",
            ),
        )

        assert concept.id is not None
        assert concept.embedding == vector
        assert concept.embedding_model == EMBEDDING_MODEL
        assert concept.embedding_input_hash == hash_embedding_input(
            "\n".join(
                [
                    "Type: Concept",
                    "Code: TEST_CONCEPT",
                    "Name: Test concept",
                    "Description: Test concept description",
                ],
            ),
        )

        persisted = await session.scalar(
            select(Concept).where(Concept.code == "TEST_CONCEPT"),
        )
        assert persisted is concept
    finally:
        monkeypatch.undo()


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
async def test_register_concept_leaves_commit_boundary_to_caller(
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
            await register_concept(
                writer,
                ConceptCreate(
                    code="TEST_NO_COMMIT_CONCEPT",
                    name="No commit concept",
                    description="Visible only after caller commit",
                ),
            )

            async with session_factory() as reader:
                before_commit = await reader.scalar(
                    select(Concept).where(Concept.code == "TEST_NO_COMMIT_CONCEPT"),
                )
                assert before_commit is None

            await writer.commit()

        async with session_factory() as reader:
            after_commit = await reader.scalar(
                select(Concept).where(Concept.code == "TEST_NO_COMMIT_CONCEPT"),
            )
            assert after_commit is not None
            await reader.delete(after_commit)
            await reader.commit()
    finally:
        monkeypatch.undo()


@pytest.mark.asyncio
async def test_register_concept_embed_failure_leaves_no_partial_write(
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
            with pytest.raises(RuntimeError, match="embedding unavailable"):
                await register_concept(
                    writer,
                    ConceptCreate(
                        code="TEST_EMBED_FAIL_CONCEPT",
                        name="Embed fail concept",
                        description="Should not persist",
                    ),
                )

            assert list(writer.new) == []
            await writer.rollback()

        async with session_factory() as reader:
            persisted = await reader.scalar(
                select(Concept).where(Concept.code == "TEST_EMBED_FAIL_CONCEPT"),
            )
            assert persisted is None
    finally:
        monkeypatch.undo()


@pytest.mark.asyncio
async def test_register_concept_serializes_same_session_concurrent_calls(
    session: AsyncSession,
) -> None:
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
        concept_a, concept_b = await asyncio.gather(
            register_concept(
                session,
                ConceptCreate(
                    code="TEST_CONCURRENT_A",
                    name="Concurrent A",
                    description="First concurrent write",
                ),
            ),
            register_concept(
                session,
                ConceptCreate(
                    code="TEST_CONCURRENT_B",
                    name="Concurrent B",
                    description="Second concurrent write",
                ),
            ),
        )

        rows = list(
            (
                await session.execute(
                    select(Concept).where(
                        Concept.code.in_(["TEST_CONCURRENT_A", "TEST_CONCURRENT_B"]),
                    ),
                )
            ).scalars().all(),
        )

        assert {row.code for row in rows} == {"TEST_CONCURRENT_A", "TEST_CONCURRENT_B"}
        assert concept_a.embedding == [1.0] * EMBEDDING_DIMENSIONS
        assert concept_b.embedding == [2.0] * EMBEDDING_DIMENSIONS
        assert concept_a.embedding_input_hash != concept_b.embedding_input_hash
    finally:
        monkeypatch.undo()


@pytest.mark.asyncio
async def test_register_indicator_populates_embedding_fields_from_parent_context(
    session: AsyncSession,
) -> None:
    geography = await session.scalar(select(Geography).where(Geography.code == "USA"))
    assert geography is not None

    concept = Concept(
        code="TEST_FAMILY_CONCEPT",
        name="Test family concept",
        description="Parent concept description",
    )
    session.add(concept)
    await session.flush()

    expected_text = "\n".join(
        [
            "Type: Indicator",
            "Code: TEST_FAMILY",
            "Name: Test family",
            "Description: Test family description",
            "Geography: United States",
            "Concept: Test family concept (TEST_FAMILY_CONCEPT)",
            "Concept description: Parent concept description",
        ],
    )
    vector = [0.5] * EMBEDDING_DIMENSIONS

    monkeypatch = pytest.MonkeyPatch()

    async def fake_embed_text(text: str) -> list[float]:
        assert text == expected_text
        return vector

    monkeypatch.setattr(
        "macro_foundry.services.registration.embed_text",
        fake_embed_text,
    )
    try:
        family = await register_indicator(
            session,
            IndicatorCreate(
                code="TEST_FAMILY",
                name="Test family",
                description="Test family description",
                concept_id=concept.id,
                geography_id=geography.id,
            ),
        )

        assert family.id is not None
        assert family.embedding == vector
        assert family.embedding_model == EMBEDDING_MODEL
        assert family.embedding_input_hash == hash_embedding_input(expected_text)
    finally:
        monkeypatch.undo()
