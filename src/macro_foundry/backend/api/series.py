"""Hand-written routes for the series domain."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.encoders import jsonable_encoder
from pydantic import ValidationError
from sqlalchemy import Select, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from macro_foundry.backend.deps import get_session, verify_token
from macro_foundry.models import Concept, ConceptTag, Indicator, IndicatorVariant, Series
from macro_foundry.schemas import GeographyRead, SeriesCreate, SeriesRead, SeriesReadDetail, SeriesUpdate, TagRead

router = APIRouter(prefix="/series", tags=["series"])


def _series_detail_statement() -> Select[tuple[Series]]:
    return select(Series).options(
        selectinload(Series.geography),
        selectinload(Series.indicator_variant)
        .selectinload(IndicatorVariant.indicator)
        .selectinload(Indicator.concept)
        .selectinload(Concept.concept_tags)
        .selectinload(ConceptTag.tag),
    )


def _serialize_series_detail(series: Series) -> SeriesReadDetail:
    base_payload = SeriesRead.model_validate(series).model_dump()
    iv = series.indicator_variant
    concept_tags = iv.indicator.concept.concept_tags if iv and iv.indicator and iv.indicator.concept else []
    tags = sorted(
        (TagRead.model_validate(ct.tag) for ct in concept_tags if ct.tag is not None),
        key=lambda tag: tag.name,
    )
    return SeriesReadDetail(
        **base_payload,
        geography=GeographyRead.model_validate(series.geography),
        tags=tags,
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


async def _commit_series(session: AsyncSession) -> None:
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Request violates a database constraint",
        ) from exc


@router.get("/{series_id}", response_model=SeriesReadDetail)
async def get_series(
    series_id: UUID,
    session: AsyncSession = Depends(get_session),
    _: None = Depends(verify_token),
) -> SeriesReadDetail:
    series = await _get_series_by_id(session, series_id, with_detail=True)
    if series is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found")
    return _serialize_series_detail(series)


@router.post("/", response_model=SeriesRead, status_code=status.HTTP_201_CREATED)
async def create_series(
    payload: SeriesCreate,
    session: AsyncSession = Depends(get_session),
    _: None = Depends(verify_token),
) -> Series:
    await _raise_if_code_taken(session, payload.code)
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

    for field_name, field_value in update_data.items():
        setattr(series, field_name, field_value)

    await _commit_series(session)
    await session.refresh(series)
    return series


__all__ = ["router"]
