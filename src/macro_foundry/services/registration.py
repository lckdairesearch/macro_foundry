"""Embed-on-write registration helpers for semantic catalog entities."""

from __future__ import annotations

import asyncio

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from macro_foundry.enums import CategoryKind
from macro_foundry.models import Category, Geography, Series
from macro_foundry.schemas import SeriesCreate
from macro_foundry.services.embeddings import (
    EMBEDDING_MODEL,
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


class CategoryAttachmentError(ValueError):
    """A series was attached to a category that is not an attachable concept node."""


async def ensure_category_is_concept(
    session: AsyncSession,
    category_id: UUID | None,
) -> None:
    """Enforce ADR 0025 §3: a series attaches only to a `kind=concept` node.

    `None` is allowed (a draft / deliberately-unclassified series). A non-null
    `category_id` must reference an existing `kind=concept` node; a `topic`
    (browse) node or a missing node is rejected with a clear, specific error.
    This is the app-layer guardrail that the DB FK deliberately does not enforce.
    """

    if category_id is None:
        return

    category = await session.get(Category, category_id)
    if category is None:
        raise CategoryAttachmentError(
            f"category_id {category_id} does not reference an existing category",
        )
    if category.kind is not CategoryKind.CONCEPT:
        raise CategoryAttachmentError(
            "category_id must reference a kind=concept node, "
            f"got {category.kind.value} '{category.code}'",
        )


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


async def register_series(
    session: AsyncSession,
    payload: SeriesCreate,
) -> Series:
    """Create a series row with embedding metadata populated."""

    await ensure_category_is_concept(session, payload.category_id)

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
    "CategoryAttachmentError",
    "ensure_category_is_concept",
    "ensure_series_embedding_current",
    "register_series",
]
