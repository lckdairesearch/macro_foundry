"""Issue 69: governance stored-enum vocabulary follows the indicator rename.

The ``TargetType`` and ``ProposalType`` string values are *persisted* in
``change_proposal_items.target_type`` and ``change_proposals.proposal_type``
under named CHECK constraints (no native PG enums). After the
``series_family -> indicator`` rename (#68) the audit vocabulary must speak the
same language as the tables it points at, and migration 0014 must carry any
existing rows across the value rename.
"""

from __future__ import annotations

import asyncio

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from macro_foundry.config import settings
from macro_foundry.enums import ProposalType, TargetType
from macro_foundry.seed import run_seed


@pytest.mark.no_db
def test_target_type_uses_indicator_vocabulary() -> None:
    assert TargetType.INDICATORS.value == "indicators"
    assert TargetType.INDICATOR_VARIANTS.value == "indicator_variants"


@pytest.mark.no_db
def test_proposal_type_uses_indicator_vocabulary() -> None:
    assert ProposalType.ADD_INDICATOR.value == "add_indicator"


@pytest.mark.no_db
def test_old_series_family_vocabulary_is_gone() -> None:
    target_values = {member.value for member in TargetType}
    proposal_values = {member.value for member in ProposalType}

    assert "series_families" not in target_values
    assert "series_family_members" not in target_values
    assert "add_family" not in proposal_values

    assert not hasattr(TargetType, "SERIES_FAMILIES")
    assert not hasattr(TargetType, "SERIES_FAMILY_MEMBERS")
    assert not hasattr(ProposalType, "ADD_FAMILY")


_INSERT_OLD_VOCAB_PROPOSAL = """
WITH new_proposal AS (
    INSERT INTO change_proposals (title, proposal_type, status, requested_by, risk_level)
    VALUES ('issue-69 data-migration probe', 'add_family', 'proposed', 'agent', 'low')
    RETURNING id
)
INSERT INTO change_proposal_items
    (proposal_id, item_type, target_type, action, validation_status)
SELECT new_proposal.id, 'db_row', t.target_type, 'insert', 'pending'
FROM new_proposal,
    (VALUES ('series_families'), ('series_family_members'), ('series')) AS t(target_type)
RETURNING proposal_id
"""


async def _insert_old_vocab_proposal() -> None:
    engine = create_async_engine(settings.db.owner_url, pool_pre_ping=True)
    try:
        async with engine.begin() as conn:
            await conn.execute(text(_INSERT_OLD_VOCAB_PROPOSAL))
    finally:
        await engine.dispose()


async def _assert_rows_renamed_and_constraints_tightened() -> None:
    engine = create_async_engine(settings.db.owner_url, pool_pre_ping=True)
    try:
        async with engine.connect() as conn:
            proposal_types = (
                await conn.execute(
                    text(
                        "SELECT DISTINCT proposal_type FROM change_proposals "
                        "WHERE title = 'issue-69 data-migration probe'"
                    )
                )
            ).scalars().all()
            assert proposal_types == ["add_indicator"]

            target_types = sorted(
                (
                    await conn.execute(
                        text(
                            "SELECT target_type FROM change_proposal_items i "
                            "JOIN change_proposals p ON p.id = i.proposal_id "
                            "WHERE p.title = 'issue-69 data-migration probe'"
                        )
                    )
                )
                .scalars()
                .all()
            )
            # series_families -> indicators, series_family_members -> indicator_variants,
            # series (control) unchanged.
            assert target_types == ["indicator_variants", "indicators", "series"]

        # The tightened CHECK constraints must now reject the retired values.
        async with engine.begin() as conn:
            with pytest.raises(IntegrityError):
                await conn.execute(
                    text(
                        "INSERT INTO change_proposals "
                        "(title, proposal_type, status, requested_by, risk_level) "
                        "VALUES ('issue-69 reject probe', 'add_family', 'proposed', 'agent', 'low')"
                    )
                )

        # Clean up the probe rows (cascade deletes the items).
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "DELETE FROM change_proposals "
                    "WHERE title = 'issue-69 data-migration probe'"
                )
            )
    finally:
        await engine.dispose()


async def _reseed_seed_tables() -> None:
    engine = create_async_engine(settings.db.test_url, pool_pre_ping=True)
    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False, autoflush=False)
    try:
        async with session_factory() as session:
            await run_seed(session)
            await session.commit()
    finally:
        await engine.dispose()


def test_migration_0014_renames_existing_governance_rows(alembic_config: Config) -> None:
    """Rows persisted under the old vocabulary are carried across by 0014."""

    command.downgrade(alembic_config, "0013")
    try:
        asyncio.run(_insert_old_vocab_proposal())
        command.upgrade(alembic_config, "head")
        asyncio.run(_assert_rows_renamed_and_constraints_tightened())
    finally:
        command.upgrade(alembic_config, "head")
        # Upgrading back to head re-runs 0015_tags_code, whose DELETE FROM tags
        # empties the shared session seed; restore it for later tests.
        asyncio.run(_reseed_seed_tables())
