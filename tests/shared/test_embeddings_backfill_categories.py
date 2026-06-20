"""WS3 (ADR 0027 consequence): `embeddings backfill` covers concept nodes.

Seeding the full taxonomy (ADR 0027) creates ~171 `kind=concept` nodes with no
embedding (the seed runner is offline — no OpenAI dependency). `macrodb embeddings
backfill` is the repair path that embeds them so concept semantic-search works. It
must embed `kind=concept` nodes (with their parent-subdomain context), never
`kind=topic` browse nodes, and be a no-op once current.

Runs against the shared session test database (conftest migrates + seeds to head).
`embed_texts` is replaced with a deterministic fake so no live OpenAI key is needed.
"""

from __future__ import annotations

from collections.abc import Sequence

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from macro_foundry.cli.embeddings import run_embeddings_backfill_with_session_factory
from macro_foundry.enums import CategoryKind
from macro_foundry.models import Category
from macro_foundry.services.embeddings import EMBEDDING_DIMENSIONS, EMBEDDING_MODEL


async def _fake_embed(texts: Sequence[str]) -> list[list[float]]:
    return [[0.125] * EMBEDDING_DIMENSIONS for _ in texts]


async def _get(session: AsyncSession, code: str) -> Category:
    category = await session.scalar(select(Category).where(Category.code == code))
    assert category is not None, code
    return category


@pytest.mark.asyncio
async def test_backfill_embeds_concept_nodes_but_not_topics(
    test_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    # Stale a seeded concept and confirm a topic node starts unembedded.
    async with test_session_factory() as session:
        concept = await _get(session, "GDP_DEFLATOR")
        assert concept.kind is CategoryKind.CONCEPT
        concept.embedding = None
        concept.embedding_model = None
        concept.embedding_input_hash = None

        topic = await _get(session, "PRICES")
        assert topic.kind is CategoryKind.TOPIC
        assert topic.embedding is None
        await session.commit()

    summary = await run_embeddings_backfill_with_session_factory(
        session_factory=test_session_factory,
        embed_batch=_fake_embed,
    )
    assert "categories" in summary
    assert summary["categories"] >= 1

    async with test_session_factory() as session:
        concept = await _get(session, "GDP_DEFLATOR")
        # The concept node now carries the embedding (ADR 0025 §1).
        assert concept.embedding is not None
        assert len(concept.embedding) == EMBEDDING_DIMENSIONS
        assert concept.embedding_model == EMBEDDING_MODEL
        assert concept.embedding_input_hash is not None

        # Topic (browse) nodes are never embedded.
        topic = await _get(session, "PRICES")
        assert topic.embedding is None


@pytest.mark.asyncio
async def test_backfill_is_idempotent_on_concepts(
    test_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    # First run embeds every stale concept; a second run finds nothing stale.
    await run_embeddings_backfill_with_session_factory(
        session_factory=test_session_factory,
        embed_batch=_fake_embed,
    )
    second = await run_embeddings_backfill_with_session_factory(
        session_factory=test_session_factory,
        embed_batch=_fake_embed,
    )
    assert second["categories"] == 0
