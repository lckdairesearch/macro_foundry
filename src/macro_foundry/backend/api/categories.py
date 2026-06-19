"""Routes for the V8 category tree.

Standard CRUD via the in-repo generator, plus recursive-CTE traversal of
`category_edges` for ancestor (topic-of) and descendant (everything-under) walks
(ADR 0025 §5). Depth <= 3 is a curation convention; the walks are not depth-bounded.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import literal, select
from sqlalchemy.ext.asyncio import AsyncSession

from macro_foundry.backend.crud import crud_router
from macro_foundry.backend.deps import get_session, verify_token
from macro_foundry.models import Category, CategoryEdge
from macro_foundry.schemas import CategoryCreate, CategoryRead, CategoryUpdate

router: APIRouter = crud_router(
    prefix="/categories",
    model=Category,
    create_schema=CategoryCreate,
    update_schema=CategoryUpdate,
    read_schema=CategoryRead,
)


async def _require_category(session: AsyncSession, category_id: UUID) -> Category:
    category = await session.scalar(select(Category).where(Category.id == category_id))
    if category is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found")
    return category


@router.get("/{category_id}/ancestors", response_model=list[CategoryRead])
async def list_category_ancestors(
    category_id: UUID,
    session: AsyncSession = Depends(get_session),
    _: None = Depends(verify_token),
) -> list[Category]:
    """Walk up the tree from a node, nearest parent first (the node's topic chain)."""

    await _require_category(session, category_id)

    edges = CategoryEdge.__table__
    walk = (
        select(
            edges.c.parent_category_id.label("category_id"),
            literal(1).label("depth"),
        )
        .where(edges.c.child_category_id == category_id)
        .cte("ancestors", recursive=True)
    )
    walk = walk.union_all(
        select(edges.c.parent_category_id, walk.c.depth + 1).join(
            walk,
            edges.c.child_category_id == walk.c.category_id,
        )
    )
    statement = select(Category).join(walk, Category.id == walk.c.category_id).order_by(walk.c.depth)
    result = await session.execute(statement)
    return list(result.scalars().all())


@router.get("/{category_id}/descendants", response_model=list[CategoryRead])
async def list_category_descendants(
    category_id: UUID,
    session: AsyncSession = Depends(get_session),
    _: None = Depends(verify_token),
) -> list[Category]:
    """Walk down the tree from a node, nearest children first (everything under it)."""

    await _require_category(session, category_id)

    edges = CategoryEdge.__table__
    walk = (
        select(
            edges.c.child_category_id.label("category_id"),
            literal(1).label("depth"),
        )
        .where(edges.c.parent_category_id == category_id)
        .cte("descendants", recursive=True)
    )
    walk = walk.union_all(
        select(edges.c.child_category_id, walk.c.depth + 1).join(
            walk,
            edges.c.parent_category_id == walk.c.category_id,
        )
    )
    statement = select(Category).join(walk, Category.id == walk.c.category_id).order_by(walk.c.depth, Category.code)
    result = await session.execute(statement)
    return list(result.scalars().all())


__all__ = ["router"]
