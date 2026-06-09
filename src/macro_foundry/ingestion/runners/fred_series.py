"""Latest-snapshot FRED import runner for curated bootstrap flows."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from macro_foundry.enums import Frequency, IngestionRunStatus, IngestionTriggeredBy
from macro_foundry.ingestion.providers.fred import FredClientProtocol, FredSeriesMetadata, fred_period_bounds
from macro_foundry.models import IngestionFeed, IngestionRunLog, Observation, SeriesSource

_DEFAULT_OVERLAPS: dict[Frequency, tuple[str, int]] = {
    Frequency.MONTHLY: ("months", 18),
    Frequency.QUARTERLY: ("quarters", 8),
    Frequency.ANNUAL: ("years", 5),
    Frequency.WEEKLY: ("weeks", 12),
    Frequency.DAILY: ("days", 35),
}


@dataclass(frozen=True, slots=True)
class FredImportOutcome:
    """Summary of one FRED raw-series latest-snapshot import."""

    series_code: str
    external_code: str
    metadata: FredSeriesMetadata
    rows_fetched: int
    rows_written: int
    rows_skipped: int
    run_log_id: UUID


async def import_fred_latest_snapshot(
    session: AsyncSession,
    *,
    client: FredClientProtocol,
    series_id: UUID,
    series_code: str,
    frequency: Frequency,
    external_code: str,
    ingestion_feed: IngestionFeed,
    series_source: SeriesSource,
    run_date: date,
    code_version: str | None,
    triggered_by: IngestionTriggeredBy = IngestionTriggeredBy.MANUAL,
) -> FredImportOutcome:
    """Import one curated FRED series into snapshot-vintage observations."""

    started_at = datetime.now(timezone.utc)
    params = ingestion_feed.request_params or {}
    observation_start = await _resolve_observation_start(
        session,
        series_id=series_id,
        frequency=frequency,
        request_params=params,
    )

    try:
        metadata = await client.fetch_series_metadata(external_code)
        if metadata.frequency is not frequency:
            raise ValueError(
                f"FRED frequency {metadata.frequency.value!r} for {external_code!r} does not match "
                f"curated series frequency {frequency.value!r}",
            )

        fetched_rows = await client.fetch_series_observations(
            external_code,
            observation_start=observation_start,
        )
        latest_by_period = await _load_latest_observations_by_period(
            session,
            series_id=series_id,
            period_starts=[
                fred_period_bounds(row.period_anchor, frequency=frequency)[0]
                for row in fetched_rows
            ],
        )

        rows_to_write: list[dict[str, Any]] = []
        rows_skipped = 0
        for row in fetched_rows:
            period_start, period_end = fred_period_bounds(
                row.period_anchor,
                frequency=frequency,
            )
            existing = latest_by_period.get(period_start)
            if existing is not None and existing.value == row.value:
                rows_skipped += 1
                continue
            rows_to_write.append(
                {
                    "series_id": series_id,
                    "period_start": period_start,
                    "period_end": period_end,
                    "value": row.value,
                    "vintage_date": run_date,
                },
            )

        run_log = IngestionRunLog(
            ingestion_feed_id=ingestion_feed.id,
            started_at=started_at,
            finished_at=datetime.now(timezone.utc),
            status=IngestionRunStatus.SUCCESS,
            rows_fetched=len(fetched_rows),
            rows_inserted=len(rows_to_write),
            rows_skipped=rows_skipped,
            triggered_by=triggered_by,
            code_version=code_version,
            parameters=_build_parameters(
                external_code=external_code,
                observation_start=observation_start,
                run_date=run_date,
            ),
            notes=f"latest-snapshot import for {series_source.external_code}",
        )
        session.add(run_log)
        await session.flush()

        if rows_to_write:
            for row in rows_to_write:
                row["ingestion_run_log_id"] = run_log.id

            statement = insert(Observation).values(rows_to_write)
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
                    "computation_run_log_id": None,
                },
            )
            await session.execute(statement)

        return FredImportOutcome(
            series_code=series_code,
            external_code=external_code,
            metadata=metadata,
            rows_fetched=len(fetched_rows),
            rows_written=len(rows_to_write),
            rows_skipped=rows_skipped,
            run_log_id=run_log.id,
        )
    except Exception as exc:
        failed_log = IngestionRunLog(
            ingestion_feed_id=ingestion_feed.id,
            started_at=started_at,
            finished_at=datetime.now(timezone.utc),
            status=IngestionRunStatus.FAILED,
            error_message=str(exc),
            triggered_by=triggered_by,
            code_version=code_version,
            parameters=_build_parameters(
                external_code=external_code,
                observation_start=observation_start,
                run_date=run_date,
            ),
            notes="latest-snapshot import failed",
        )
        session.add(failed_log)
        await session.flush()
        raise


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


async def _resolve_observation_start(
    session: AsyncSession,
    *,
    series_id: UUID,
    frequency: Frequency,
    request_params: dict[str, Any],
) -> date | None:
    latest_period_start = await session.scalar(
        select(func.max(Observation.period_start)).where(Observation.series_id == series_id),
    )
    if latest_period_start is None:
        return None

    overlap = request_params.get("overlap")
    if overlap is None:
        unit, value = _DEFAULT_OVERLAPS[frequency]
    else:
        unit = str(overlap["unit"])
        value = int(overlap["value"])

    return _shift_period_start(latest_period_start, unit=unit, value=-value)


def _shift_period_start(anchor: date, *, unit: str, value: int) -> date:
    normalized_unit = unit.lower()
    if normalized_unit in {"days", "day"}:
        from datetime import timedelta

        return anchor + timedelta(days=value)
    if normalized_unit in {"weeks", "week"}:
        from datetime import timedelta

        return anchor + timedelta(weeks=value)
    if normalized_unit in {"months", "month"}:
        return _shift_months(anchor, value)
    if normalized_unit in {"quarters", "quarter"}:
        return _shift_months(anchor, value * 3)
    if normalized_unit in {"years", "year"}:
        return _shift_months(anchor, value * 12)
    raise ValueError(f"Unsupported overlap unit {unit!r}")


def _shift_months(anchor: date, months: int) -> date:
    total_months = (anchor.year * 12 + (anchor.month - 1)) + months
    year = total_months // 12
    month = total_months % 12 + 1
    return date(year, month, 1)


def _build_parameters(
    *,
    external_code: str,
    observation_start: date | None,
    run_date: date,
) -> dict[str, str]:
    payload = {
        "series_id": external_code,
        "snapshot_vintage_date": run_date.isoformat(),
    }
    if observation_start is not None:
        payload["observation_start"] = observation_start.isoformat()
    return payload


__all__ = ["FredImportOutcome", "import_fred_latest_snapshot"]
