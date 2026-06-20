"""Issue #82: V8 category-taxonomy seed (ADR 0026 within ADR 0025 schema).

Acceptance criteria covered:
- a fresh seed yields exactly 15 domains + 71 subdomains + the universal concepts;
- the edges form a single-parent tree (every non-root has exactly one parent);
- no node exceeds depth 3;
- re-running the seed is idempotent (no duplicate codes or edges);
- universal concepts are kind=concept, domains/subdomains are kind=topic except
  the documented concept-leaf L2s.

These run against the shared session test database (conftest migrates to head
and seeds it). The ``session`` fixture rolls back, so reset/reseed is safe.
"""

from __future__ import annotations

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from macro_foundry.enums import CategoryKind
from macro_foundry.models import Category, CategoryEdge
from macro_foundry.seed import SeedTarget, reset_seed_tables, run_seed
from macro_foundry.seed.data.categories import (
    CATEGORIES,
    CONCEPTS,
    DOMAINS,
    SUBDOMAINS,
)

EXPECTED_DOMAINS = 15
EXPECTED_SUBDOMAINS = 71
EXPECTED_CONCEPTS = 157  # the full L3 long tail, seeded in full (ADR 0027)
EXPECTED_NODES = EXPECTED_DOMAINS + EXPECTED_SUBDOMAINS + EXPECTED_CONCEPTS
# Every node except the 15 roots carries exactly one parent edge.
EXPECTED_EDGES = EXPECTED_NODES - EXPECTED_DOMAINS

# The 14 documented concept-leaf L2 subdomains (kind=concept) — ADR 0026 §5.
CONCEPT_LEAF_L2_CODES = {row["code"] for row in SUBDOMAINS if row["kind"] == "concept"}


async def _count_categories(session: AsyncSession) -> int:
    return await session.scalar(select(func.count()).select_from(Category)) or 0


async def _count_edges(session: AsyncSession) -> int:
    return await session.scalar(select(func.count()).select_from(CategoryEdge)) or 0


async def _reseed_fresh(session: AsyncSession) -> None:
    await reset_seed_tables(session, only={SeedTarget.CATEGORIES})
    await session.commit()
    await run_seed(session, only={SeedTarget.CATEGORIES})
    await session.commit()


def test_seed_data_matches_expected_tier_counts() -> None:
    assert len(DOMAINS) == EXPECTED_DOMAINS
    assert len(SUBDOMAINS) == EXPECTED_SUBDOMAINS
    assert len(CONCEPTS) == EXPECTED_CONCEPTS
    assert len(CATEGORIES) == EXPECTED_NODES
    # Codes are unique across the whole tree.
    codes = [row["code"] for row in CATEGORIES]
    assert len(codes) == len(set(codes))


def test_concept_leaf_l2s_are_the_documented_fourteen() -> None:
    assert CONCEPT_LEAF_L2_CODES == {
        "COMMODITY_PRICE",
        "INPUT_OUTPUT",
        "SECTORAL_OUTPUT",
        "CONSUMER_CONFIDENCE",
        "HOUSEHOLD_SPENDING",
        "FINANCIAL_CONDITIONS",
        "FISCAL_BALANCE",
        "EXCHANGE_RATE",
        "HEALTH_EXPENDITURE",
        "ENROLLMENT_AND_PARTICIPATION",
        "EDUCATION_EXPENDITURE",
        "WELLBEING",
        "BASIC_SERVICES_ACCESS",
        "UNCLASSIFIED",
    }


def test_concepts_cover_headlines_and_the_long_tail() -> None:
    concept_codes = {row["code"] for row in CONCEPTS}
    # Universal headlines (ADR 0026 §5) — GDP maps to the real/nominal tiers
    # (no bare GDP concept exists) — AND the deeper long tail now seeded in full
    # (ADR 0027), e.g. CPI_CORE / GDP_DEFLATOR that previously had to accrete.
    assert {
        "CPI_ALL_ITEMS",
        "GDP_REAL",
        "GDP_NOMINAL",
        "UNEMPLOYMENT_RATE",
        "POLICY_RATE",
        "CPI_CORE",
        "GDP_DEFLATOR",
    }.issubset(concept_codes)
    assert all(row["kind"] == "concept" for row in CONCEPTS)
    # The L3 concepts parent only onto seeded subdomains (no orphan edges).
    subdomain_codes = {row["code"] for row in SUBDOMAINS}
    assert all(row["parent_code"] in subdomain_codes for row in CONCEPTS)


@pytest.mark.asyncio
async def test_fresh_seed_yields_exact_domain_subdomain_concept_counts(
    session: AsyncSession,
) -> None:
    await _reseed_fresh(session)

    domains = await session.scalar(
        select(func.count())
        .select_from(Category)
        .outerjoin(CategoryEdge, CategoryEdge.child_category_id == Category.id)
        .where(CategoryEdge.id.is_(None)),
    )
    assert domains == EXPECTED_DOMAINS

    total = await _count_categories(session)
    assert total == EXPECTED_NODES
    assert await _count_edges(session) == EXPECTED_EDGES


@pytest.mark.asyncio
async def test_seed_forms_a_single_parent_tree(session: AsyncSession) -> None:
    await _reseed_fresh(session)

    # Every non-root node has exactly one parent edge; no node has two.
    duplicate_children = await session.scalar(
        select(func.count()).select_from(
            select(CategoryEdge.child_category_id)
            .group_by(CategoryEdge.child_category_id)
            .having(func.count() > 1)
            .subquery(),
        ),
    )
    assert duplicate_children == 0

    # Edge count equals (nodes - roots): every non-root is parented exactly once.
    assert await _count_edges(session) == EXPECTED_NODES - EXPECTED_DOMAINS


@pytest.mark.asyncio
async def test_no_node_exceeds_depth_three(session: AsyncSession) -> None:
    await _reseed_fresh(session)

    rows = (
        await session.execute(
            select(Category.code, Category.id),
        )
    ).all()
    id_by_code = {code: cid for code, cid in rows}
    parent_of = {
        child: parent
        for child, parent in (
            await session.execute(
                select(CategoryEdge.child_category_id, CategoryEdge.parent_category_id),
            )
        ).all()
    }

    for code, node_id in id_by_code.items():
        depth = 1
        current = node_id
        while current in parent_of:
            current = parent_of[current]
            depth += 1
            assert depth <= 3, f"{code} exceeds depth 3"


@pytest.mark.asyncio
async def test_node_kinds_match_topic_skeleton_and_concept_grain(
    session: AsyncSession,
) -> None:
    await _reseed_fresh(session)

    kinds = dict(
        (
            await session.execute(select(Category.code, Category.kind))
        ).all(),
    )

    # Domains are all topics.
    for row in DOMAINS:
        assert kinds[row["code"]] == CategoryKind.TOPIC

    # Subdomains are topics except the documented concept-leaf L2s.
    for row in SUBDOMAINS:
        expected = CategoryKind.CONCEPT if row["code"] in CONCEPT_LEAF_L2_CODES else CategoryKind.TOPIC
        assert kinds[row["code"]] == expected

    # The full L3 concept tail is all concepts.
    for row in CONCEPTS:
        assert kinds[row["code"]] == CategoryKind.CONCEPT


@pytest.mark.asyncio
async def test_reseed_is_idempotent_on_counts(session: AsyncSession) -> None:
    await _reseed_fresh(session)
    nodes_before = await _count_categories(session)
    edges_before = await _count_edges(session)

    summary = await run_seed(session, only={SeedTarget.CATEGORIES})
    await session.commit()

    assert await _count_categories(session) == nodes_before
    assert await _count_edges(session) == edges_before
    # Second run inserts nothing — only updates existing rows.
    assert summary[SeedTarget.CATEGORIES].inserted == 0


@pytest.mark.asyncio
async def test_seed_restores_a_mutated_category_node(session: AsyncSession) -> None:
    await _reseed_fresh(session)

    prices = await session.scalar(select(Category).where(Category.code == "PRICES"))
    assert prices is not None
    prices.name = "Prices (mutated)"
    await session.commit()

    summary = await run_seed(session, only={SeedTarget.CATEGORIES})
    await session.commit()

    restored = await session.scalar(select(Category).where(Category.code == "PRICES"))
    assert restored is not None
    await session.refresh(restored)
    assert restored.name == "Prices"
    assert summary[SeedTarget.CATEGORIES].updated > 0
