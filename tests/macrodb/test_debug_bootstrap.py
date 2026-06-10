"""Integration coverage for the request-centric debug bootstrap."""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from typer.testing import CliRunner

from macro_foundry.bootstrap import DebugSmokeBootstrapResult, EnvTarget, run_debug_smoke_bootstrap
from macro_foundry.cli import app
from macro_foundry.enums import IngestionRunStatus
from macro_foundry.models import (
    IngestionFeed,
    IngestionFeedMember,
    IngestionRunLog,
    IngestionRunLogMember,
    Observation,
    Series,
    SeriesHierarchyEdge,
)

runner = CliRunner()


@pytest.mark.asyncio
async def test_debug_bootstrap_exercises_request_feed_provenance_and_hierarchy(
    test_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    summary = await run_debug_smoke_bootstrap(
        database=EnvTarget.TEST,
        session_factory=test_session_factory,
        run_date=date(2026, 6, 9),
    )

    assert summary.database is EnvTarget.TEST
    assert summary.feed_members == 2
    assert summary.member_logs == 2
    assert summary.observations == 2
    assert summary.hierarchy_edges == 1

    async with test_session_factory() as session:
        feed = await session.scalar(
            select(IngestionFeed).where(IngestionFeed.endpoint_url == "/debug/shared-table"),
        )
        assert feed is not None
        assert feed.request_params == {"dataset": "debug-smoke"}

        members = (
            await session.execute(
                select(IngestionFeedMember)
                .where(IngestionFeedMember.ingestion_feed_id == feed.id)
                .order_by(IngestionFeedMember.execution_order),
            )
        ).scalars().all()
        assert [member.selector_type for member in members] == ["json_path", "json_path"]
        assert [member.selector_config for member in members] == [
            {"path": "$.rows[0].value"},
            {"path": "$.rows[1].value"},
        ]

        run_log = await session.scalar(
            select(IngestionRunLog).where(IngestionRunLog.ingestion_feed_id == feed.id),
        )
        assert run_log is not None
        assert run_log.status is IngestionRunStatus.SUCCESS

        member_logs = (
            await session.execute(
                select(IngestionRunLogMember)
                .where(IngestionRunLogMember.ingestion_run_log_id == run_log.id)
                .order_by(IngestionRunLogMember.created_at),
            )
        ).scalars().all()
        assert len(member_logs) == 2
        assert {member_log.ingestion_feed_member_id for member_log in member_logs} == {
            member.id for member in members
        }

        observations = (
            await session.execute(
                select(Observation).where(
                    Observation.ingestion_run_log_member_id.in_(
                        member_log.id for member_log in member_logs
                    ),
                ),
            )
        ).scalars().all()
        assert len(observations) == 2
        assert {row.ingestion_run_log_member_id for row in observations} == {
            member_log.id for member_log in member_logs
        }

        parent = await session.scalar(select(Series).where(Series.code == "DEBUG_TOTAL_INDEX"))
        child = await session.scalar(select(Series).where(Series.code == "DEBUG_COMPONENT_A_INDEX"))
        assert parent is not None
        assert child is not None
        edge = await session.scalar(
            select(SeriesHierarchyEdge).where(
                SeriesHierarchyEdge.parent_series_id == parent.id,
                SeriesHierarchyEdge.child_series_id == child.id,
            ),
        )
        assert edge is not None


@pytest.mark.no_db
def test_debug_bootstrap_cli_reports_request_centric_smoke_summary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_bootstrap_database(
        *,
        target: EnvTarget,
        reset: bool,
        preset: str,
    ) -> DebugSmokeBootstrapResult:
        assert target is EnvTarget.TEST
        assert reset is False
        assert preset == "debug-smoke"
        return DebugSmokeBootstrapResult(
            database=target,
            run_date=date(2026, 6, 9),
            feed_members=2,
            member_logs=2,
            observations=2,
            hierarchy_edges=1,
        )

    monkeypatch.setattr(
        "macro_foundry.cli._helpers._bootstrap_database",
        fake_bootstrap_database,
    )

    result = runner.invoke(app, ["db", "bootstrap", "debug-smoke", "--target", "test"])

    assert result.exit_code == 0
    assert "target=test" in result.output
    assert "run_date=2026-06-09" in result.output
    assert "preset=debug-smoke" in result.output
    assert "request_feed_members=2" in result.output
    assert "observations=2" in result.output
