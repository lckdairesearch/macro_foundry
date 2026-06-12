"""Embed-on-write registration helpers for semantic catalog entities."""

from __future__ import annotations

import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from macro_foundry.models import Concept, Geography, Series, Indicator, IndicatorVariant
from macro_foundry.schemas import ConceptCreate, SeriesCreate, IndicatorCreate
from macro_foundry.services.embeddings import (
    EMBEDDING_MODEL,
    compose_concept_embedding_input,
    compose_indicator_embedding_input,
    compose_series_embedding_input,
    embed_text,
    hash_embedding_input,
)


def _registration_lock(session: AsyncSession) -> asyncio.Lock:
    lock = session.info.get("_registration_lock")
    if isinstance(lock, asyncio.Lock):
        return lock
    new_lock = asyncio.Lock()
    session.info["_registration_lock"] = new_lock
    return new_lock


async def ensure_series_embedding_current(
    session: AsyncSession,
    series: Series,
) -> Series:
    """Recompute a series embedding when its live composition has gone stale."""

    async with _registration_lock(session):
        hydrated = await session.scalar(
            select(Series)
            .execution_options(populate_existing=True)
            .options(
                selectinload(Series.geography),
                selectinload(Series.indicator_variant)
                .selectinload(IndicatorVariant.indicator)
                .selectinload(Indicator.concept),
            )
            .where(Series.id == series.id),
        )

    if hydrated is None:
        raise ValueError(f"Series {series.id} not found for embedding refresh")

    text = compose_series_embedding_input(hydrated)
    expected_hash = hash_embedding_input(text)
    if (
        hydrated.embedding is not None
        and hydrated.embedding_model == EMBEDDING_MODEL
        and hydrated.embedding_input_hash == expected_hash
    ):
        return hydrated

    hydrated.embedding = await embed_text(text)
    hydrated.embedding_model = EMBEDDING_MODEL
    hydrated.embedding_input_hash = expected_hash
    async with _registration_lock(session):
        await session.flush()
    return hydrated


async def register_concept(
    session: AsyncSession,
    payload: ConceptCreate,
) -> Concept:
    """Create a concept row with embedding metadata populated."""

    concept = Concept(**payload.model_dump())
    text = compose_concept_embedding_input(concept)
    concept.embedding = await embed_text(text)
    concept.embedding_model = EMBEDDING_MODEL
    concept.embedding_input_hash = hash_embedding_input(text)
    async with _registration_lock(session):
        session.add(concept)
        await session.flush()
    return concept


async def register_indicator(
    session: AsyncSession,
    payload: IndicatorCreate,
) -> Indicator:
    """Create an indicator row with embedding metadata populated."""

    async with _registration_lock(session):
        concept = await session.get(Concept, payload.concept_id)
        geography = await session.get(Geography, payload.geography_id)

    indicator = Indicator(**payload.model_dump())
    indicator.concept = concept
    indicator.geography = geography
    text = compose_indicator_embedding_input(indicator)
    indicator.embedding = await embed_text(text)
    indicator.embedding_model = EMBEDDING_MODEL
    indicator.embedding_input_hash = hash_embedding_input(text)
    async with _registration_lock(session):
        session.add(indicator)
        await session.flush()
    return indicator


async def register_series(
    session: AsyncSession,
    payload: SeriesCreate,
) -> Series:
    """Create a series row with embedding metadata populated."""

    async with _registration_lock(session):
        geography = await session.get(Geography, payload.geography_id)

    series = Series(**payload.model_dump())
    series.geography = geography
    text = compose_series_embedding_input(series)
    series.embedding = await embed_text(text)
    series.embedding_model = EMBEDDING_MODEL
    series.embedding_input_hash = hash_embedding_input(text)
    async with _registration_lock(session):
        session.add(series)
        await session.flush()
    return series


__all__ = [
    "ensure_series_embedding_current",
    "register_concept",
    "register_indicator",
    "register_series",
]
