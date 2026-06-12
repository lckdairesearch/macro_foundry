"""Routes for canonical series hierarchy edges."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from macro_foundry.backend.deps import get_session, verify_token
from macro_foundry.models import Series, Indicator, IndicatorVariant, SeriesHierarchyEdge
from macro_foundry.schemas import SeriesHierarchyEdgeCreate, SeriesHierarchyEdgeRead, SeriesHierarchyEdgeUpdate

router = APIRouter(prefix="/series-hierarchy-edges", tags=["series-hierarchy-edges"])


async def _fetch_edge(session: AsyncSession, edge_id: UUID) -> SeriesHierarchyEdge | None:
    return await session.scalar(select(SeriesHierarchyEdge).where(SeriesHierarchyEdge.id == edge_id))


async def _concept_id_for_series(session: AsyncSession, series_id: UUID) -> UUID | None:
    statement = (
        select(Indicator.concept_id)
        .join(IndicatorVariant, IndicatorVariant.indicator_id == Indicator.id)
        .where(IndicatorVariant.series_id == series_id)
    )
    return await session.scalar(statement)


async def _validate_same_concept_edge(session: AsyncSession, parent_series_id: UUID, child_series_id: UUID) -> None:
    if parent_series_id == child_series_id:
        raise HTTPException(
            status_code=422,
            detail="parent_series_id and child_series_id must differ",
        )

    parent = await session.scalar(select(Series).where(Series.id == parent_series_id))
    child = await session.scalar(select(Series).where(Series.id == child_series_id))
    if parent is None or child is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Series not found")

    parent_concept_id = await _concept_id_for_series(session, parent_series_id)
    child_concept_id = await _concept_id_for_series(session, child_series_id)
    if parent_concept_id is None or child_concept_id is None:
        raise HTTPException(
            status_code=422,
            detail="Both hierarchy endpoints must belong to an indicator",
        )
    if parent_concept_id != child_concept_id:
        raise HTTPException(
            status_code=422,
            detail="Series hierarchy edges must stay within one concept",
        )


async def _commit_or_conflict(session: AsyncSession) -> None:
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Request violates a database constraint",
        ) from exc


@router.get("/", response_model=list[SeriesHierarchyEdgeRead])
async def list_series_hierarchy_edges(
    session: AsyncSession = Depends(get_session),
    _: None = Depends(verify_token),
    parent_series_id: UUID | None = None,
    child_series_id: UUID | None = None,
    limit: int = Query(default=100, ge=0, le=1000),
    offset: int = Query(default=0, ge=0),
) -> list[SeriesHierarchyEdge]:
    statement = select(SeriesHierarchyEdge).order_by(
        SeriesHierarchyEdge.parent_series_id,
        SeriesHierarchyEdge.sort_order,
        SeriesHierarchyEdge.child_series_id,
    )
    if parent_series_id is not None:
        statement = statement.where(SeriesHierarchyEdge.parent_series_id == parent_series_id)
    if child_series_id is not None:
        statement = statement.where(SeriesHierarchyEdge.child_series_id == child_series_id)
    result = await session.execute(statement.limit(limit).offset(offset))
    return list(result.scalars().all())


@router.get("/{edge_id}", response_model=SeriesHierarchyEdgeRead)
async def get_series_hierarchy_edge(
    edge_id: UUID,
    session: AsyncSession = Depends(get_session),
    _: None = Depends(verify_token),
) -> SeriesHierarchyEdge:
    edge = await _fetch_edge(session, edge_id)
    if edge is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found")
    return edge


@router.post("/", response_model=SeriesHierarchyEdgeRead, status_code=status.HTTP_201_CREATED)
async def create_series_hierarchy_edge(
    payload: SeriesHierarchyEdgeCreate,
    session: AsyncSession = Depends(get_session),
    _: None = Depends(verify_token),
) -> SeriesHierarchyEdge:
    await _validate_same_concept_edge(session, payload.parent_series_id, payload.child_series_id)
    edge = SeriesHierarchyEdge(**payload.model_dump(exclude_unset=True))
    session.add(edge)
    await _commit_or_conflict(session)
    await session.refresh(edge)
    return edge


@router.patch("/{edge_id}", response_model=SeriesHierarchyEdgeRead)
async def update_series_hierarchy_edge(
    edge_id: UUID,
    payload: SeriesHierarchyEdgeUpdate,
    session: AsyncSession = Depends(get_session),
    _: None = Depends(verify_token),
) -> SeriesHierarchyEdge:
    edge = await _fetch_edge(session, edge_id)
    if edge is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found")

    update_data = payload.model_dump(exclude_unset=True)
    parent_series_id = update_data.get("parent_series_id", edge.parent_series_id)
    child_series_id = update_data.get("child_series_id", edge.child_series_id)
    if "parent_series_id" in update_data or "child_series_id" in update_data:
        await _validate_same_concept_edge(session, parent_series_id, child_series_id)

    for field_name, field_value in update_data.items():
        setattr(edge, field_name, field_value)

    await _commit_or_conflict(session)
    await session.refresh(edge)
    return edge


@router.delete("/{edge_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_series_hierarchy_edge(
    edge_id: UUID,
    session: AsyncSession = Depends(get_session),
    _: None = Depends(verify_token),
) -> Response:
    edge = await _fetch_edge(session, edge_id)
    if edge is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found")
    await session.delete(edge)
    await _commit_or_conflict(session)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


__all__ = ["router"]
