"""Generic feed executor for selector-registry ingestion."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from macro_foundry.enums import IngestionRunStatus, IngestionTriggeredBy
from macro_foundry.ingestion.runtime.selectors import get_selector
from macro_foundry.ingestion.runtime.types import Selector
from macro_foundry.models import IngestionFeed, IngestionFeedMember, IngestionRunLog, IngestionRunLogMember, Observation


@dataclass(frozen=True, slots=True)
class FeedExecutionOutcome:
    """Summary of one generic feed execution."""

    run_log_id: UUID
    status: IngestionRunStatus
    rows_fetched: int
    rows_inserted: int
    rows_skipped: int


async def execute_feed(
    session: AsyncSession,
    feed_id: UUID,
    *,
    payload: Any,
    selectors: dict[str, Selector] | None = None,
    run_date: date,
    triggered_by: IngestionTriggeredBy = IngestionTriggeredBy.MANUAL,
    code_version: str | None = None,
    parameters: dict[str, Any] | None = None,
) -> FeedExecutionOutcome:
    """Execute one active ingestion feed against a shared provider payload."""

    started_at = datetime.now(timezone.utc)
    selector_registry = selectors or {}
    feed = await _load_feed(session, feed_id)
    if feed is None:
        raise ValueError(f"IngestionFeed {feed_id} was not found")
    if not feed.is_active:
        raise ValueError(f"IngestionFeed {feed_id} is inactive")

    active_members = sorted(
        (member for member in feed.members if member.is_active),
        key=lambda member: (member.execution_order is None, member.execution_order or 0, str(member.id)),
    )

    run_log = IngestionRunLog(
        ingestion_feed_id=feed.id,
        started_at=started_at,
        status=IngestionRunStatus.SUCCESS,
        rows_fetched=0,
        rows_inserted=0,
        rows_skipped=0,
        triggered_by=triggered_by,
        code_version=code_version,
        parameters=parameters if parameters is not None else feed.request_params,
    )
    session.add(run_log)
    await session.flush()

    total_fetched = 0
    total_inserted = 0
    total_skipped = 0
    failed_members = 0

    for member in active_members:
        selector = selector_registry.get(member.selector_type) or get_selector(member.selector_type)
        member_rows_fetched, member_rows_inserted, member_rows_skipped, member_failed = await _execute_member(
            session,
            payload=payload,
            selector=selector,
            member=member,
            run_log=run_log,
            run_date=run_date,
        )
        total_fetched += member_rows_fetched
        total_inserted += member_rows_inserted
        total_skipped += member_rows_skipped
        failed_members += int(member_failed)

    run_log.rows_fetched = total_fetched
    run_log.rows_inserted = total_inserted
    run_log.rows_skipped = total_skipped
    run_log.finished_at = datetime.now(timezone.utc)
    if failed_members == len(active_members) and active_members:
        run_log.status = IngestionRunStatus.FAILED
    elif failed_members:
        run_log.status = IngestionRunStatus.PARTIAL
    else:
        run_log.status = IngestionRunStatus.SUCCESS
    await session.flush()

    return FeedExecutionOutcome(
        run_log_id=run_log.id,
        status=run_log.status,
        rows_fetched=total_fetched,
        rows_inserted=total_inserted,
        rows_skipped=total_skipped,
    )


async def _execute_member(
    session: AsyncSession,
    *,
    payload: Any,
    selector: Selector,
    member: IngestionFeedMember,
    run_log: IngestionRunLog,
    run_date: date,
) -> tuple[int, int, int, bool]:
    config = member.selector_config or {}
    validation = selector.validate(config)
    if not validation.is_valid:
        return await _record_failed_member(
            session,
            member=member,
            run_log=run_log,
            error_message="; ".join(validation.errors),
            diagnostics={"selector_type": member.selector_type, "outcome": "config_error"},
        )

    result = selector.extract(payload, config)
    if result.outcome == "provider_error":
        return await _record_failed_member(
            session,
            member=member,
            run_log=run_log,
            error_message=result.error_message or "provider error",
            diagnostics={
                "selector_type": member.selector_type,
                "outcome": result.outcome,
                **(result.diagnostics or {}),
            },
        )

    latest_by_period = await _load_latest_observations_by_period(
        session,
        series_id=member.series_source.series_id,
        period_starts=[observation.period_start for observation in result.observations],
    )
    rows_to_write: list[dict[str, Any]] = []
    rows_skipped = 0
    for observation in result.observations:
        existing = latest_by_period.get(observation.period_start)
        if existing is not None and existing.value == observation.value:
            rows_skipped += 1
            continue
        rows_to_write.append(
            {
                "series_id": member.series_source.series_id,
                "period_start": observation.period_start,
                "period_end": observation.period_end,
                "value": observation.value,
                "vintage_date": observation.vintage_date or run_date,
            },
        )

    member_log = IngestionRunLogMember(
        ingestion_run_log_id=run_log.id,
        ingestion_feed_member_id=member.id,
        status=IngestionRunStatus.SUCCESS,
        rows_fetched=len(result.observations),
        rows_inserted=len(rows_to_write),
        rows_skipped=rows_skipped,
        diagnostics={"selector_type": member.selector_type, "outcome": result.outcome},
    )
    session.add(member_log)
    await session.flush()

    if rows_to_write:
        for row in rows_to_write:
            row["ingestion_run_log_member_id"] = member_log.id
            row["computation_run_log_id"] = None
        statement = insert(Observation).values(rows_to_write)
        excluded = statement.excluded
        statement = statement.on_conflict_do_update(
            index_elements=[Observation.series_id, Observation.period_start, Observation.vintage_date],
            set_={
                "period_end": excluded.period_end,
                "value": excluded.value,
                "ingestion_run_log_member_id": excluded.ingestion_run_log_member_id,
                "computation_run_log_id": None,
            },
        )
        await session.execute(statement)

    return len(result.observations), len(rows_to_write), rows_skipped, False


async def _record_failed_member(
    session: AsyncSession,
    *,
    member: IngestionFeedMember,
    run_log: IngestionRunLog,
    error_message: str,
    diagnostics: dict[str, Any],
) -> tuple[int, int, int, bool]:
    session.add(
        IngestionRunLogMember(
            ingestion_run_log_id=run_log.id,
            ingestion_feed_member_id=member.id,
            status=IngestionRunStatus.FAILED,
            rows_fetched=0,
            rows_inserted=0,
            rows_skipped=0,
            error_message=error_message,
            diagnostics=diagnostics,
        ),
    )
    await session.flush()
    return 0, 0, 0, True


async def _load_feed(session: AsyncSession, feed_id: UUID) -> IngestionFeed | None:
    return await session.scalar(
        select(IngestionFeed)
        .where(IngestionFeed.id == feed_id)
        .options(
            selectinload(IngestionFeed.members).selectinload(IngestionFeedMember.series_source),
        ),
    )


async def _load_latest_observations_by_period(
    session: AsyncSession,
    *,
    series_id: UUID,
    period_starts: list[date],
) -> dict[date, Observation]:
    unique_period_starts = sorted(set(period_starts))
    if not unique_period_starts:
        return {}

    rows = (
        await session.execute(
            select(Observation)
            .where(
                Observation.series_id == series_id,
                Observation.period_start.in_(unique_period_starts),
            )
            .order_by(Observation.period_start, Observation.vintage_date.desc()),
        )
    ).scalars()

    latest_by_period: dict[date, Observation] = {}
    for row in rows:
        latest_by_period.setdefault(row.period_start, row)
    return latest_by_period


__all__ = ["FeedExecutionOutcome", "execute_feed"]
