"""Issue #83: concept accretion via the registration service (ADR 0025/0026 §5).

`register_concept_node` is the chokepoint by which the long tail of `kind=concept`
nodes accretes under the seeded subdomain skeleton as series arrive: a universal
concept already seeded under a subdomain is returned untouched, a not-yet-existing
concept is minted as a `kind=concept` node + a `category_edge` under its parent and
carries an embedding (ADR 0025 §1). The parent subdomain must exist — no
placeholders (ADR 0010).

Runs against the shared session test database (conftest migrates + seeds to head).
The seeded skeleton provides `CONSUMER_PRICES` (subdomain) and `CPI_ALL_ITEMS`
(universal concept) used as fixtures here. `embed_text` is mocked so no live
OpenAI key is needed.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from macro_foundry.enums import CategoryKind
from macro_foundry.models import Category, CategoryEdge
from macro_foundry.services.embeddings import EMBEDDING_DIMENSIONS, EMBEDDING_MODEL
from macro_foundry.services.registration import (
    CategoryAttachmentError,
    register_concept_node,
)


@pytest.fixture(autouse=True)
def _mock_embed_text(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_embed_text(text: str) -> list[float]:
        fill = float((sum(ord(ch) for ch in text) % 13) + 1)
        return [fill] * EMBEDDING_DIMENSIONS

    monkeypatch.setattr("macro_foundry.services.registration.embed_text", fake_embed_text)


async def _edge_for(session: AsyncSession, child_id: object) -> CategoryEdge | None:
    return await session.scalar(
        select(CategoryEdge).where(CategoryEdge.child_category_id == child_id),
    )


@pytest.mark.asyncio
async def test_mints_new_concept_under_seeded_subdomain(session: AsyncSession) -> None:
    concept = await register_concept_node(
        session,
        code="CPI_CORE",
        name="CPI Core",
        parent_code="CONSUMER_PRICES",
        description="Consumer prices excluding food and energy (core inflation).",
    )

    assert concept.kind is CategoryKind.CONCEPT
    assert concept.code == "CPI_CORE"
    # Carries an embedding (ADR 0025 §1: the concept node holds it now).
    assert concept.embedding is not None
    assert concept.embedding_model == EMBEDDING_MODEL
    assert concept.embedding_input_hash is not None

    # Linked under CONSUMER_PRICES via exactly one edge (strict tree).
    parent = await session.scalar(select(Category).where(Category.code == "CONSUMER_PRICES"))
    edge = await _edge_for(session, concept.id)
    assert edge is not None
    assert edge.parent_category_id == parent.id


@pytest.mark.asyncio
async def test_accretion_is_idempotent_on_code(session: AsyncSession) -> None:
    first = await register_concept_node(
        session, code="CPI_CORE", name="CPI Core", parent_code="CONSUMER_PRICES",
    )
    second = await register_concept_node(
        session, code="CPI_CORE", name="CPI Core (again)", parent_code="CONSUMER_PRICES",
    )

    assert first.id == second.id
    edges = (
        await session.execute(
            select(CategoryEdge).where(CategoryEdge.child_category_id == first.id),
        )
    ).scalars().all()
    assert len(edges) == 1  # no duplicate edge minted


@pytest.mark.asyncio
async def test_returns_seeded_universal_concept_untouched(session: AsyncSession) -> None:
    seeded = await session.scalar(select(Category).where(Category.code == "CPI_ALL_ITEMS"))
    assert seeded is not None

    result = await register_concept_node(
        session, code="CPI_ALL_ITEMS", name="CPI All Items", parent_code="CONSUMER_PRICES",
    )

    assert result.id == seeded.id
    # No second edge created for an already-seeded node.
    edges = (
        await session.execute(
            select(CategoryEdge).where(CategoryEdge.child_category_id == seeded.id),
        )
    ).scalars().all()
    assert len(edges) == 1


@pytest.mark.asyncio
async def test_missing_parent_subdomain_is_rejected(session: AsyncSession) -> None:
    with pytest.raises(CategoryAttachmentError, match="does not exist"):
        await register_concept_node(
            session, code="SOME_NEW_CONCEPT", name="X", parent_code="NO_SUCH_SUBDOMAIN",
        )


@pytest.mark.asyncio
async def test_existing_topic_code_is_not_returned_as_concept(session: AsyncSession) -> None:
    # CONSUMER_PRICES is a seeded kind=topic node; minting a concept with that
    # code must be rejected, not silently treated as attachable.
    with pytest.raises(CategoryAttachmentError, match="not an attachable concept"):
        await register_concept_node(
            session, code="CONSUMER_PRICES", name="X", parent_code="PRICES",
        )
