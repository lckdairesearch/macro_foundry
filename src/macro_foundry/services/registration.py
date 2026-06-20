"""Embed-on-write registration helpers for semantic catalog entities."""

from __future__ import annotations

import asyncio

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from macro_foundry.enums import CategoryKind
from macro_foundry.models import Category, CategoryEdge, Geography, Series
from macro_foundry.schemas import SeriesCreate
from macro_foundry.services.embeddings import (
    EMBEDDING_MODEL,
    compose_category_embedding_input,
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


async def register_concept_node(
    session: AsyncSession,
    *,
    code: str,
    name: str,
    parent_code: str,
    description: str | None = None,
) -> Category:
    """Find-or-mint the `kind=concept` node a series will attach to (ADR 0025/0026).

    Concepts accrete as series arrive: a universal concept seeded under the
    subdomain skeleton is returned as-is; a not-yet-existing concept is minted as
    a `kind=concept` node, embedded (ADR 0025 §1 — the concept node carries the
    embedding that lived on the V7 `concepts` table), and linked under its parent
    subdomain via a `category_edge`. Idempotent on `categories.code`.

    The parent subdomain must already exist (seeded skeleton). Minting a concept
    under a missing parent — or returning a node that is not itself a concept —
    is rejected rather than papered over with a placeholder (ADR 0010).
    """

    async with _registration_lock(session):
        existing = await session.scalar(select(Category).where(Category.code == code))
    if existing is not None:
        if existing.kind is not CategoryKind.CONCEPT:
            raise CategoryAttachmentError(
                f"category '{code}' already exists as kind={existing.kind.value}, "
                "not an attachable concept node",
            )
        return existing

    async with _registration_lock(session):
        parent = await session.scalar(select(Category).where(Category.code == parent_code))
    if parent is None:
        raise CategoryAttachmentError(
            f"parent subdomain '{parent_code}' for concept '{code}' does not exist; "
            "seed the subdomain skeleton before accreting concepts",
        )

    concept = Category(
        code=code,
        name=name,
        description=description,
        kind=CategoryKind.CONCEPT,
    )
    text = compose_category_embedding_input(concept, parent_name=parent.name)
    concept.embedding = await embed_text(text)
    concept.embedding_model = EMBEDDING_MODEL
    concept.embedding_input_hash = hash_embedding_input(text)

    async with _registration_lock(session):
        session.add(concept)
        await session.flush()
        next_sort_order = await session.scalar(
            select(func.count())
            .select_from(CategoryEdge)
            .where(CategoryEdge.parent_category_id == parent.id),
        )
        session.add(
            CategoryEdge(
                parent_category_id=parent.id,
                child_category_id=concept.id,
                sort_order=next_sort_order,
            ),
        )
        await session.flush()
    return concept


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
    "register_concept_node",
    "register_series",
]
