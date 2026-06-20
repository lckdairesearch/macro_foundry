"""Hand-written routes for the series domain."""

from __future__ import annotations

from collections.abc import Iterable
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.encoders import jsonable_encoder
from pydantic import ValidationError
from sqlalchemy import Select, literal, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from macro_foundry.backend.deps import get_session, verify_token
from macro_foundry.models import Category, CategoryEdge, Series
from macro_foundry.schemas import CategoryRead, GeographyRead, SeriesCreate, SeriesRead, SeriesReadDetail, SeriesUpdate
from macro_foundry.services.registration import CategoryAttachmentError, ensure_category_is_concept

router = APIRouter(prefix="/series", tags=["series"])


def _series_detail_statement() -> Select[tuple[Series]]:
    return select(Series).options(
        selectinload(Series.geography),
    )


async def _category_paths_for(
    session: AsyncSession,
    category_ids: Iterable[UUID | None],
) -> dict[UUID, list[Category]]:
    """Walk each category up `category_edges`, most-specific first (ADR 0025 §1).

    One recursive CTE for the whole input set: row 0 of each path is the node
    itself (the attached concept), then each ancestor up to the domain root. This
    is explicit and eager — it never relies on relationship lazy-loading.
    """

    unique_ids = {cid for cid in category_ids if cid is not None}
    if not unique_ids:
        return {}

    edges = CategoryEdge.__table__
    walk = (
        select(
            Category.id.label("origin_id"),
            Category.id.label("category_id"),
            literal(0).label("depth"),
        )
        .where(Category.id.in_(unique_ids))
        .cte("series_category_path", recursive=True)
    )
    walk = walk.union_all(
        select(
            walk.c.origin_id,
            edges.c.parent_category_id,
            walk.c.depth + 1,
        ).join(walk, edges.c.child_category_id == walk.c.category_id),
    )
    statement = (
        select(walk.c.origin_id, Category)
        .join(Category, Category.id == walk.c.category_id)
        .order_by(walk.c.origin_id, walk.c.depth)
    )

    paths: dict[UUID, list[Category]] = {}
    for origin_id, category in await session.execute(statement):
        paths.setdefault(origin_id, []).append(category)
    return paths


def _serialize_series_detail(
    series: Series,
    category_path: list[Category],
) -> SeriesReadDetail:
    base_payload = SeriesRead.model_validate(series).model_dump()
    return SeriesReadDetail(
        **base_payload,
        geography=GeographyRead.model_validate(series.geography),
        category_path=[CategoryRead.model_validate(node) for node in category_path],
    )


async def _get_series_by_id(
    session: AsyncSession,
    series_id: UUID,
    *,
    with_detail: bool = False,
) -> Series | None:
    statement = _series_detail_statement() if with_detail else select(Series)
    result = await session.execute(statement.where(Series.id == series_id))
    return result.scalar_one_or_none()


async def _raise_if_code_taken(
    session: AsyncSession,
    code: str,
    *,
    exclude_id: UUID | None = None,
) -> None:
    statement = select(Series.id).where(Series.code == code)
    if exclude_id is not None:
        statement = statement.where(Series.id != exclude_id)
    existing_id = await session.scalar(statement)
    if existing_id is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Series code '{code}' already exists",
        )


async def _ensure_category_attachable(
    session: AsyncSession,
    category_id: UUID | None,
) -> None:
    """Reject attaching a series to a non-concept node (ADR 0025 §3, app-side)."""
    try:
        await ensure_category_is_concept(session, category_id)
    except CategoryAttachmentError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc


async def _commit_series(session: AsyncSession) -> None:
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Request violates a database constraint",
        ) from exc


@router.get("/", response_model=list[SeriesReadDetail])
async def list_series(
    category_id: UUID | None = None,
    geography_id: UUID | None = None,
    session: AsyncSession = Depends(get_session),
    _: None = Depends(verify_token),
) -> list[SeriesReadDetail]:
    """Derived reads over the V8 category attachment (ADR 0025 §3).

    The "indicator" grain is not a stored row but the query
    `series WHERE category_id = ? AND geography_id = ?`. The cross-geography
    concept read drops the geography filter. Both are expressed here as optional
    filters.
    """

    statement = _series_detail_statement()
    if category_id is not None:
        statement = statement.where(Series.category_id == category_id)
    if geography_id is not None:
        statement = statement.where(Series.geography_id == geography_id)
    statement = statement.order_by(Series.code)

    result = await session.execute(statement)
    rows = result.scalars().all()
    paths = await _category_paths_for(session, (series.category_id for series in rows))
    return [_serialize_series_detail(series, paths.get(series.category_id, [])) for series in rows]


@router.get("/{series_id}", response_model=SeriesReadDetail)
async def get_series(
    series_id: UUID,
    session: AsyncSession = Depends(get_session),
    _: None = Depends(verify_token),
) -> SeriesReadDetail:
    series = await _get_series_by_id(session, series_id, with_detail=True)
    if series is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found")
    paths = await _category_paths_for(session, [series.category_id])
    return _serialize_series_detail(series, paths.get(series.category_id, []))


@router.post("/", response_model=SeriesRead, status_code=status.HTTP_201_CREATED)
async def create_series(
    payload: SeriesCreate,
    session: AsyncSession = Depends(get_session),
    _: None = Depends(verify_token),
) -> Series:
    await _raise_if_code_taken(session, payload.code)
    await _ensure_category_attachable(session, payload.category_id)
    series = Series(**payload.model_dump())
    session.add(series)
    await _commit_series(session)
    await session.refresh(series)
    return series


@router.patch("/{series_id}", response_model=SeriesRead)
async def update_series(
    series_id: UUID,
    payload: SeriesUpdate,
    session: AsyncSession = Depends(get_session),
    _: None = Depends(verify_token),
) -> Series:
    series = await _get_series_by_id(session, series_id)
    if series is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found")

    update_data = payload.model_dump(exclude_unset=True)
    if "code" in update_data and update_data["code"] != series.code:
        await _raise_if_code_taken(session, update_data["code"], exclude_id=series.id)

    merged_payload = {
        field_name: getattr(series, field_name)
        for field_name in SeriesCreate.model_fields
    }
    merged_payload.update(update_data)
    try:
        SeriesCreate.model_validate(merged_payload)
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=jsonable_encoder(exc.errors()),
        ) from exc

    if "category_id" in update_data:
        await _ensure_category_attachable(session, update_data["category_id"])

    for field_name, field_value in update_data.items():
        setattr(series, field_name, field_value)

    await _commit_series(session)
    await session.refresh(series)
    return series


__all__ = ["router"]
