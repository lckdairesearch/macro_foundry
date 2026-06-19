"""Issue #78: migration 0017 drops the V7 conceptual spine (ADR 0025 §1).

The five spine tables are gone at head, and the governance CHECK constraints no
longer admit the vocabulary that pointed at them. These run against the shared
session test database, which conftest migrates to head.
"""

from __future__ import annotations

import asyncio

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine

from macro_foundry.config import settings

_DROPPED_TABLES = ("concepts", "indicators", "indicator_variants", "tags", "concept_tags")


async def _assert_spine_tables_absent() -> None:
    engine = create_async_engine(settings.db.owner_url, pool_pre_ping=True)
    try:
        async with engine.connect() as conn:
            rows = await conn.exec_driver_sql(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
                """,
            )
            table_names = {row[0] for row in rows}
        for dropped in _DROPPED_TABLES:
            assert dropped not in table_names
    finally:
        await engine.dispose()


async def _assert_target_type_rejected(value: str) -> None:
    engine = create_async_engine(settings.db.owner_url, pool_pre_ping=True)
    try:
        async with engine.begin() as conn:
            with pytest.raises(IntegrityError):
                await conn.execute(
                    text(
                        """
                        WITH p AS (
                            INSERT INTO change_proposals
                                (title, proposal_type, status, requested_by, risk_level)
                            VALUES ('issue-78 reject probe', 'add_provider_series',
                                    'proposed', 'agent', 'low')
                            RETURNING id
                        )
                        INSERT INTO change_proposal_items
                            (proposal_id, item_type, target_type, action, validation_status)
                        SELECT p.id, 'db_row', :value, 'insert', 'pending' FROM p
                        """,
                    ),
                    {"value": value},
                )
    finally:
        await engine.dispose()


async def _assert_proposal_type_rejected(value: str) -> None:
    engine = create_async_engine(settings.db.owner_url, pool_pre_ping=True)
    try:
        async with engine.begin() as conn:
            with pytest.raises(IntegrityError):
                await conn.execute(
                    text(
                        "INSERT INTO change_proposals "
                        "(title, proposal_type, status, requested_by, risk_level) "
                        "VALUES ('issue-78 reject probe', :value, 'proposed', 'agent', 'low')"
                    ),
                    {"value": value},
                )
    finally:
        await engine.dispose()


def test_spine_tables_absent_at_head() -> None:
    asyncio.run(_assert_spine_tables_absent())


@pytest.mark.parametrize("value", ["concepts", "indicators", "tags", "indicator_variants"])
def test_dropped_target_type_values_rejected(value: str) -> None:
    asyncio.run(_assert_target_type_rejected(value))


@pytest.mark.parametrize("value", ["add_indicator", "add_concept"])
def test_dropped_proposal_type_values_rejected(value: str) -> None:
    asyncio.run(_assert_proposal_type_rejected(value))
