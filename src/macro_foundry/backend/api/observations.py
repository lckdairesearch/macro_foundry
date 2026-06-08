"""Hand-written routes for the observations domain."""

from __future__ import annotations

from datetime import date
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from fastapi.encoders import jsonable_encoder
from pydantic import ValidationError
from sqlalchemy import select, tuple_
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from macro_foundry.backend.deps import get_session, verify_token
from macro_foundry.models import ComputationRunLog, IngestionRunLog, Observation, Series
from macro_foundry.schemas import ObservationBulkError, ObservationBulkResult, ObservationCreate, ObservationRead

router = APIRouter(prefix="/observations", tags=["observations"])


async def _commit_observations(session: AsyncSession) -> None:
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Request violates a database constraint",
        ) from exc


async def _existing_ids(
    session: AsyncSession,
    model: type[Any],
    ids: set[UUID],
) -> set[UUID]:
    if not ids:
        return set()
    result = await session.execute(select(model.id).where(model.id.in_(ids)))
    return set(result.scalars().all())


@router.get("/", response_model=list[ObservationRead])
async def list_observations(
    session: AsyncSession = Depends(get_session),
    _: None = Depends(verify_token),
    series_id: UUID | None = None,
    vintage_date: date | None = None,
    period_start_from: date | None = None,
    period_start_to: date | None = None,
    period_end_from: date | None = None,
    period_end_to: date | None = None,
    limit: int = Query(default=100, ge=0, le=1000),
    offset: int = Query(default=0, ge=0),
) -> list[Observation]:
    statement = select(Observation).order_by(
        Observation.series_id,
        Observation.period_start,
        Observation.vintage_date,
    )
    if series_id is not None:
        statement = statement.where(Observation.series_id == series_id)
    if vintage_date is not None:
        statement = statement.where(Observation.vintage_date == vintage_date)
    if period_start_from is not None:
        statement = statement.where(Observation.period_start >= period_start_from)
    if period_start_to is not None:
        statement = statement.where(Observation.period_start <= period_start_to)
    if period_end_from is not None:
        statement = statement.where(Observation.period_end >= period_end_from)
    if period_end_to is not None:
        statement = statement.where(Observation.period_end <= period_end_to)

    result = await session.execute(statement.limit(limit).offset(offset))
    return list(result.scalars().all())


@router.post("/bulk", response_model=ObservationBulkResult)
async def bulk_upsert_observations(
    payloads: list[dict[str, Any]] = Body(...),
    session: AsyncSession = Depends(get_session),
    _: None = Depends(verify_token),
) -> ObservationBulkResult:
    errors: list[ObservationBulkError] = []
    validated_rows: list[tuple[int, ObservationCreate]] = []
    seen_keys: set[tuple[UUID, date, date]] = set()

    for index, raw_payload in enumerate(payloads):
        try:
            row = ObservationCreate.model_validate(raw_payload)
        except ValidationError as exc:
            errors.append(
                ObservationBulkError(
                    index=index,
                    detail=jsonable_encoder(exc.errors()),
                ),
            )
            continue

        key = (row.series_id, row.period_start, row.vintage_date)
        if key in seen_keys:
            errors.append(
                ObservationBulkError(
                    index=index,
                    detail="Duplicate observation key within request",
                ),
            )
            continue
        seen_keys.add(key)
        validated_rows.append((index, row))

    existing_series_ids = await _existing_ids(
        session,
        Series,
        {row.series_id for _, row in validated_rows},
    )
    existing_ingestion_run_log_ids = await _existing_ids(
        session,
        IngestionRunLog,
        {
            row.ingestion_run_log_id
            for _, row in validated_rows
            if row.ingestion_run_log_id is not None
        },
    )
    existing_computation_run_log_ids = await _existing_ids(
        session,
        ComputationRunLog,
        {
            row.computation_run_log_id
            for _, row in validated_rows
            if row.computation_run_log_id is not None
        },
    )

    accepted_rows: list[ObservationCreate] = []
    for index, row in validated_rows:
        if row.series_id not in existing_series_ids:
            errors.append(ObservationBulkError(index=index, detail="series_id does not reference an existing series"))
            continue
        if row.ingestion_run_log_id is not None and row.ingestion_run_log_id not in existing_ingestion_run_log_ids:
            errors.append(
                ObservationBulkError(
                    index=index,
                    detail="ingestion_run_log_id does not reference an existing ingestion run log",
                ),
            )
            continue
        if (
            row.computation_run_log_id is not None
            and row.computation_run_log_id not in existing_computation_run_log_ids
        ):
            errors.append(
                ObservationBulkError(
                    index=index,
                    detail="computation_run_log_id does not reference an existing computation run log",
                ),
            )
            continue
        accepted_rows.append(row)

    inserted = 0
    updated = 0

    if accepted_rows:
        key_values = [
            (row.series_id, row.period_start, row.vintage_date)
            for row in accepted_rows
        ]
        existing_result = await session.execute(
            select(
                Observation.series_id,
                Observation.period_start,
                Observation.vintage_date,
            ).where(
                tuple_(
                    Observation.series_id,
                    Observation.period_start,
                    Observation.vintage_date,
                ).in_(key_values),
            ),
        )
        existing_keys = set(existing_result.all())
        inserted = sum(1 for key in key_values if key not in existing_keys)
        updated = len(key_values) - inserted

        statement = insert(Observation).values(
            [row.model_dump() for row in accepted_rows],
        )
        excluded = statement.excluded
        statement = statement.on_conflict_do_update(
            index_elements=[
                Observation.series_id,
                Observation.period_start,
                Observation.vintage_date,
            ],
            set_={
                "period_end": excluded.period_end,
                "value": excluded.value,
                "ingestion_run_log_id": excluded.ingestion_run_log_id,
                "computation_run_log_id": excluded.computation_run_log_id,
            },
        )
        await session.execute(statement)
        await _commit_observations(session)

    return ObservationBulkResult(
        received=len(payloads),
        accepted=len(accepted_rows),
        inserted=inserted,
        updated=updated,
        invalid=len(errors),
        errors=errors,
    )


__all__ = ["router"]
