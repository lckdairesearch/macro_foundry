"""Issue 81: provider-side source groups + source-group members (ADR 0025 §4).

`source_groups` is a typed, self-nesting publication unit owned by a
`provider_catalog`; `source_group_members` links `series_sources` into those
groups (M:N, so one source can sit in many groups). Indentation is DERIVED, not
stored. Governance gains `source_groups` as a `target_type`.

These vertical slices assert the schema-level contract: the FKs, the two UNIQUEs,
the self-parent CHECK, the self-nesting and multi-group behaviours, eager loading
(no `MissingGreenlet`), and that the migration round-trips the widened
`target_type` CHECK.
"""

from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from macro_foundry.config import settings
from macro_foundry.enums import (
    Frequency,
    Measure,
    OriginType,
    ProviderRole,
    ProviderType,
    SeasonalAdjustment,
    SourceGroupType,
    TargetType,
    TemporalStockFlow,
    UnitKind,
    UnitScale,
)
from macro_foundry.models import (
    Geography,
    Provider,
    ProviderCatalog,
    Series,
    SeriesSource,
    SourceGroup,
    SourceGroupMember,
)
from macro_foundry.seed import run_seed


async def _seeded_country(session: AsyncSession, *, code: str = "USA") -> Geography:
    geography = await session.scalar(select(Geography).where(Geography.code == code))
    assert geography is not None
    return geography


async def _create_catalog(
    session: AsyncSession,
    *,
    provider_name: str,
    catalog_name: str = "Source Group Catalog",
) -> ProviderCatalog:
    provider = Provider(name=provider_name, type=ProviderType.OFFICIAL, is_active=True)
    session.add(provider)
    await session.commit()
    await session.refresh(provider)

    catalog = ProviderCatalog(provider_id=provider.id, name=catalog_name, is_placeholder=False)
    session.add(catalog)
    await session.commit()
    await session.refresh(catalog)
    return catalog


async def _create_series_source(
    session: AsyncSession,
    *,
    series_code: str,
    catalog: ProviderCatalog,
) -> SeriesSource:
    geography = await _seeded_country(session)
    series = Series(
        code=series_code,
        name=f"{series_code} name",
        origin_type=OriginType.INGESTED,
        geography_id=geography.id,
        frequency=Frequency.MONTHLY,
        temporal_stock_flow=TemporalStockFlow.INDEX,
        unit_kind=UnitKind.INDEX,
        unit_scale=UnitScale.ONE,
        measure=Measure.LEVEL,
        annualized=False,
        seasonal_adjustment=SeasonalAdjustment.NSA,
        is_active=True,
    )
    session.add(series)
    await session.commit()
    await session.refresh(series)

    source = SeriesSource(
        series_id=series.id,
        provider_catalog_id=catalog.id,
        external_code=f"{series_code}-EXT",
        priority=1,
        provider_role=ProviderRole.PRIMARY_SOURCE,
    )
    session.add(source)
    await session.commit()
    await session.refresh(source)
    return source


@pytest.mark.asyncio
async def test_release_group_nests_table_groups(session: AsyncSession) -> None:
    catalog = await _create_catalog(session, provider_name="MF Nesting Provider")

    release = SourceGroup(
        provider_catalog_id=catalog.id,
        group_type=SourceGroupType.RELEASE,
        code="rid=21",
        name="Employment Situation",
    )
    session.add(release)
    await session.commit()
    await session.refresh(release)

    table_a = SourceGroup(
        provider_catalog_id=catalog.id,
        parent_group_id=release.id,
        group_type=SourceGroupType.TABLE,
        code="B-1",
        name="Table B-1",
    )
    table_b = SourceGroup(
        provider_catalog_id=catalog.id,
        parent_group_id=release.id,
        group_type=SourceGroupType.TABLE,
        code="B-2",
        name="Table B-2",
    )
    session.add_all([table_a, table_b])
    await session.commit()

    # Self-nesting: the release owns both table groups. Tree traversal uses an
    # explicit selectinload (the codebase convention for self-referential trees,
    # mirroring Geography.parent/child); the structure is verified in a fresh
    # session so identity-map staleness from the inserts above does not mask it.
    bind = session.bind
    async with AsyncSession(bind=bind, expire_on_commit=False) as fresh:
        refreshed = await fresh.scalar(
            select(SourceGroup)
            .options(selectinload(SourceGroup.child_groups))
            .where(SourceGroup.id == release.id),
        )
        assert refreshed is not None
        child_names = sorted(child.name for child in refreshed.child_groups)
        assert child_names == ["Table B-1", "Table B-2"]
        assert all(child.parent_group_id == release.id for child in refreshed.child_groups)

        child = await fresh.scalar(
            select(SourceGroup)
            .options(selectinload(SourceGroup.parent_group))
            .where(SourceGroup.code == "B-1"),
        )
        assert child is not None
        assert child.parent_group is not None
        assert child.parent_group.name == "Employment Situation"


@pytest.mark.asyncio
async def test_series_source_belongs_to_multiple_groups(session: AsyncSession) -> None:
    catalog = await _create_catalog(session, provider_name="MF Multi-Group Provider")
    source = await _create_series_source(session, series_code="MF_MULTI_GROUP", catalog=catalog)

    release = SourceGroup(
        provider_catalog_id=catalog.id,
        group_type=SourceGroupType.RELEASE,
        code="rel",
        name="A release",
    )
    dashboard = SourceGroup(
        provider_catalog_id=catalog.id,
        group_type=SourceGroupType.DASHBOARD,
        code="dash",
        name="A dashboard",
    )
    session.add_all([release, dashboard])
    await session.commit()

    session.add_all(
        [
            SourceGroupMember(source_group_id=release.id, series_source_id=source.id, row_label="row 1"),
            SourceGroupMember(source_group_id=dashboard.id, series_source_id=source.id, sort_order=3),
        ],
    )
    await session.commit()

    memberships = (
        await session.execute(
            select(SourceGroupMember).where(SourceGroupMember.series_source_id == source.id),
        )
    ).scalars().all()
    assert len(memberships) == 2
    # Eager-loaded relationships resolve without a MissingGreenlet.
    assert {m.source_group.code for m in memberships} == {"rel", "dash"}
    assert {m.series_source.external_code for m in memberships} == {"MF_MULTI_GROUP-EXT"}


@pytest.mark.asyncio
async def test_source_group_code_is_unique_within_catalog(session: AsyncSession) -> None:
    catalog = await _create_catalog(session, provider_name="MF Unique Code Provider")

    session.add(
        SourceGroup(
            provider_catalog_id=catalog.id,
            group_type=SourceGroupType.RELEASE,
            code="dup",
            name="First",
        ),
    )
    await session.commit()

    session.add(
        SourceGroup(
            provider_catalog_id=catalog.id,
            group_type=SourceGroupType.TABLE,
            code="dup",
            name="Second",
        ),
    )
    with pytest.raises(IntegrityError):
        await session.commit()
    await session.rollback()


@pytest.mark.asyncio
async def test_source_group_member_is_unique_per_group_and_source(session: AsyncSession) -> None:
    catalog = await _create_catalog(session, provider_name="MF Unique Member Provider")
    source = await _create_series_source(session, series_code="MF_UNIQUE_MEMBER", catalog=catalog)

    group = SourceGroup(
        provider_catalog_id=catalog.id,
        group_type=SourceGroupType.TABLE,
        code="t",
        name="A table",
    )
    session.add(group)
    await session.commit()

    session.add(SourceGroupMember(source_group_id=group.id, series_source_id=source.id))
    await session.commit()

    session.add(SourceGroupMember(source_group_id=group.id, series_source_id=source.id))
    with pytest.raises(IntegrityError):
        await session.commit()
    await session.rollback()


@pytest.mark.asyncio
async def test_source_group_requires_existing_provider_catalog(session: AsyncSession) -> None:
    session.add(
        SourceGroup(
            provider_catalog_id=uuid4(),
            group_type=SourceGroupType.OTHER,
            name="Orphan group",
        ),
    )
    with pytest.raises(IntegrityError):
        await session.commit()
    await session.rollback()


@pytest.mark.asyncio
async def test_source_group_member_requires_existing_series_source(session: AsyncSession) -> None:
    catalog = await _create_catalog(session, provider_name="MF Member FK Provider")
    group = SourceGroup(
        provider_catalog_id=catalog.id,
        group_type=SourceGroupType.TABLE,
        code="t",
        name="A table",
    )
    session.add(group)
    await session.commit()

    session.add(SourceGroupMember(source_group_id=group.id, series_source_id=uuid4()))
    with pytest.raises(IntegrityError):
        await session.commit()
    await session.rollback()


@pytest.mark.asyncio
async def test_source_group_member_cascades_on_group_delete(session: AsyncSession) -> None:
    catalog = await _create_catalog(session, provider_name="MF Cascade Provider")
    source = await _create_series_source(session, series_code="MF_CASCADE", catalog=catalog)

    group = SourceGroup(
        provider_catalog_id=catalog.id,
        group_type=SourceGroupType.TABLE,
        code="t",
        name="A table",
    )
    session.add(group)
    await session.commit()
    session.add(SourceGroupMember(source_group_id=group.id, series_source_id=source.id))
    await session.commit()

    await session.delete(group)
    await session.commit()

    remaining = (
        await session.execute(
            select(SourceGroupMember).where(SourceGroupMember.series_source_id == source.id),
        )
    ).scalars().all()
    assert remaining == []


def test_target_type_admits_source_groups() -> None:
    assert TargetType.SOURCE_GROUPS.value == "source_groups"
    assert "source_groups" in {member.value for member in TargetType}


_INSERT_SOURCE_GROUP_TARGET = """
WITH new_proposal AS (
    INSERT INTO change_proposals (title, proposal_type, status, requested_by, risk_level)
    VALUES ('issue-81 source-group target probe', 'add_provider_series', 'proposed', 'agent', 'low')
    RETURNING id
)
INSERT INTO change_proposal_items
    (proposal_id, item_type, target_type, action, validation_status)
SELECT new_proposal.id, 'db_row', 'source_groups', 'insert', 'pending'
FROM new_proposal
"""


async def _assert_source_groups_target_accepted_and_self_parent_rejected() -> None:
    engine = create_async_engine(settings.db.owner_url, pool_pre_ping=True)
    try:
        async with engine.begin() as conn:
            await conn.execute(text(_INSERT_SOURCE_GROUP_TARGET))

        async with engine.connect() as conn:
            target_types = (
                await conn.execute(
                    text(
                        "SELECT i.target_type FROM change_proposal_items i "
                        "JOIN change_proposals p ON p.id = i.proposal_id "
                        "WHERE p.title = 'issue-81 source-group target probe'"
                    )
                )
            ).scalars().all()
            assert target_types == ["source_groups"]

        # The self-parent CHECK must reject parent_group_id = id. Seed a catalog so
        # the provider FK is satisfied, then attempt the self-reference.
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO providers (name, type, is_active) "
                    "VALUES ('issue-81 self-parent provider', 'official', true)"
                )
            )
            catalog_id = (
                await conn.execute(
                    text(
                        "INSERT INTO provider_catalogs (provider_id, name, is_placeholder) "
                        "SELECT id, 'issue-81 catalog', false FROM providers "
                        "WHERE name = 'issue-81 self-parent provider' RETURNING id"
                    )
                )
            ).scalar_one()
            group_id = (
                await conn.execute(
                    text(
                        "INSERT INTO source_groups (provider_catalog_id, group_type, name) "
                        "VALUES (:catalog_id, 'release', 'self-parent probe') RETURNING id"
                    ),
                    {"catalog_id": catalog_id},
                )
            ).scalar_one()

        async with engine.begin() as conn:
            with pytest.raises(IntegrityError):
                await conn.execute(
                    text("UPDATE source_groups SET parent_group_id = id WHERE id = :id"),
                    {"id": group_id},
                )

        # Clean up the probe rows (cascade deletes proposal items + the catalog group).
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "DELETE FROM change_proposals "
                    "WHERE title = 'issue-81 source-group target probe'"
                )
            )
            await conn.execute(
                text("DELETE FROM source_groups WHERE id = :id"),
                {"id": group_id},
            )
            await conn.execute(
                text("DELETE FROM provider_catalogs WHERE id = :id"),
                {"id": catalog_id},
            )
            await conn.execute(
                text("DELETE FROM providers WHERE name = 'issue-81 self-parent provider'")
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


def test_migration_0019_round_trips_source_group_layer(alembic_config: Config) -> None:
    """0019 creates both tables and widens the target_type CHECK; down/up round-trips.

    Downgrade to 0018 must drop both tables and narrow the CHECK back; upgrading to
    head restores them. The probe asserts the widened CHECK accepts `source_groups`
    and that the self-parent CHECK rejects a self-reference.
    """

    command.downgrade(alembic_config, "0018")
    try:
        asyncio.run(_assert_source_groups_dropped())
    finally:
        command.upgrade(alembic_config, "head")
        asyncio.run(_reseed_seed_tables())

    asyncio.run(_assert_source_groups_target_accepted_and_self_parent_rejected())


async def _assert_source_groups_dropped() -> None:
    engine = create_async_engine(settings.db.owner_url, pool_pre_ping=True)
    try:
        async with engine.connect() as conn:
            rows = await conn.exec_driver_sql(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_name IN ('source_groups', 'source_group_members')
                """,
            )
            assert {row[0] for row in rows} == set()

            # The narrowed CHECK must reject `source_groups` after the downgrade.
            with pytest.raises(IntegrityError):
                async with engine.begin() as begin_conn:
                    await begin_conn.execute(
                        text(
                            "WITH p AS ("
                            "INSERT INTO change_proposals "
                            "(title, proposal_type, status, requested_by, risk_level) "
                            "VALUES ('issue-81 downgrade probe', 'add_provider_series', "
                            "'proposed', 'agent', 'low') RETURNING id) "
                            "INSERT INTO change_proposal_items "
                            "(proposal_id, item_type, target_type, action, validation_status) "
                            "SELECT p.id, 'db_row', 'source_groups', 'insert', 'pending' FROM p"
                        )
                    )
    finally:
        await engine.dispose()
