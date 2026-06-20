"""Category-taxonomy seed runner (ADR 0026 within ADR 0025 schema).

Two-phase, mirroring ``runners/geographies.py``: first upsert the category
nodes (idempotent ``on_conflict_do_update`` keyed on ``categories.code``), then
resolve parent/child ids by code and upsert the tree edges (idempotent
``on_conflict_do_update`` keyed on ``category_edges.child_category_id`` — the
single-parent unique key). Re-running is a no-op on row counts.
"""

from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from macro_foundry.enums import CategoryKind
from macro_foundry.models import Category, CategoryEdge
from macro_foundry.schemas import CategoryCreate
from macro_foundry.seed._shared import SeedOutcome
from macro_foundry.seed.data.categories import CATEGORIES, CategorySeed


def _build_category_payload(seed: CategorySeed) -> dict[str, object]:
    payload = CategoryCreate(
        code=seed["code"],
        name=seed["name"],
        kind=CategoryKind(seed["kind"]),
    )
    return payload.model_dump()


async def _load_category_ids(session: AsyncSession, codes: Iterable[str]) -> dict[str, object]:
    rows = await session.execute(
        select(Category.code, Category.id).where(Category.code.in_(tuple(codes))),
    )
    return {code: category_id for code, category_id in rows}


async def _upsert_category_nodes(session: AsyncSession, payloads: list[dict[str, object]]) -> SeedOutcome:
    if not payloads:
        return SeedOutcome()

    codes = [str(payload["code"]) for payload in payloads]
    existing_codes = set((await session.execute(select(Category.code).where(Category.code.in_(codes)))).scalars())

    statement = insert(Category).values(payloads)
    statement = statement.on_conflict_do_update(
        index_elements=[Category.code],
        set_={
            "name": statement.excluded.name,
            "kind": statement.excluded.kind,
            "updated_at": func.now(),
        },
    )
    await session.execute(statement)
    await session.flush()
    return SeedOutcome(
        inserted=len(codes) - len(existing_codes),
        updated=len(existing_codes),
    )


async def _upsert_category_edges(session: AsyncSession, payloads: list[dict[str, object]]) -> SeedOutcome:
    if not payloads:
        return SeedOutcome()

    child_ids = [payload["child_category_id"] for payload in payloads]
    existing_children = set(
        (
            await session.execute(
                select(CategoryEdge.child_category_id).where(CategoryEdge.child_category_id.in_(child_ids)),
            )
        ).scalars(),
    )

    statement = insert(CategoryEdge).values(payloads)
    statement = statement.on_conflict_do_update(
        index_elements=[CategoryEdge.child_category_id],
        set_={
            "parent_category_id": statement.excluded.parent_category_id,
            "sort_order": statement.excluded.sort_order,
            "updated_at": func.now(),
        },
    )
    await session.execute(statement)
    await session.flush()
    return SeedOutcome(
        inserted=len(child_ids) - len(existing_children),
        updated=len(existing_children),
    )


async def seed_categories(session: AsyncSession) -> SeedOutcome:
    """Seed the V8 category taxonomy: domains, subdomains, and universal concepts.

    Builds the strict single-parent tree as ``category_edges`` with a stable
    ``sort_order`` per parent (the order nodes appear in the seed data).
    """

    outcome = SeedOutcome()

    node_payloads = [_build_category_payload(seed) for seed in CATEGORIES]
    outcome.absorb(await _upsert_category_nodes(session, node_payloads))

    category_ids = await _load_category_ids(session, (seed["code"] for seed in CATEGORIES))

    sort_counters: dict[str, int] = {}
    edge_payloads: list[dict[str, object]] = []
    for seed in CATEGORIES:
        parent_code = seed.get("parent_code")
        if parent_code is None:
            continue  # roots carry no edge
        sort_order = sort_counters.get(parent_code, 0)
        sort_counters[parent_code] = sort_order + 1
        edge_payloads.append(
            {
                "parent_category_id": category_ids[parent_code],
                "child_category_id": category_ids[seed["code"]],
                "sort_order": sort_order,
            },
        )

    outcome.absorb(await _upsert_category_edges(session, edge_payloads))
    return outcome


__all__ = ["seed_categories"]
