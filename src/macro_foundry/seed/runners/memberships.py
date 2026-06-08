"""Geography-membership seed runner."""

from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from macro_foundry.models import Geography, GeographyMembership
from macro_foundry.schemas import GeographyMembershipCreate
from macro_foundry.seed._shared import SeedOutcome, assign_if_changed
from macro_foundry.seed.data.memberships import GEOGRAPHY_MEMBERSHIPS


def _membership_key(member_geography_id: object, group_geography_id: object, start_date: date | None) -> tuple[object, object, date | None]:
    return (member_geography_id, group_geography_id, start_date)


async def seed_geography_memberships(session: AsyncSession) -> SeedOutcome:
    """Seed curated bloc and subnational-region memberships."""

    geography_codes = {
        *(membership["member_code"] for membership in GEOGRAPHY_MEMBERSHIPS),
        *(membership["group_code"] for membership in GEOGRAPHY_MEMBERSHIPS),
    }
    rows = await session.execute(
        select(Geography.code, Geography.id).where(Geography.code.in_(tuple(geography_codes))),
    )
    geography_ids = {code: geography_id for code, geography_id in rows}

    missing_codes = sorted(geography_codes - set(geography_ids))
    if missing_codes:
        raise ValueError(f"Membership seed references unknown geographies: {missing_codes}")

    existing_memberships = (
        await session.execute(select(GeographyMembership))
    ).scalars()

    existing_by_key: dict[tuple[object, object, date | None], GeographyMembership] = {}
    for membership in existing_memberships:
        key = _membership_key(
            membership.member_geography_id,
            membership.group_geography_id,
            membership.start_date,
        )
        if key in existing_by_key:
            raise ValueError(
                "Duplicate geography_memberships rows found for the same natural key "
                f"member_geography_id={membership.member_geography_id} "
                f"group_geography_id={membership.group_geography_id} "
                f"start_date={membership.start_date!r}",
            )
        existing_by_key[key] = membership

    outcome = SeedOutcome()
    updatable_fields = ("end_date",)

    for membership in GEOGRAPHY_MEMBERSHIPS:
        payload = GeographyMembershipCreate(
            member_geography_id=geography_ids[membership["member_code"]],
            group_geography_id=geography_ids[membership["group_code"]],
            start_date=membership.get("start_date"),
            end_date=membership.get("end_date"),
        ).model_dump()
        key = _membership_key(
            payload["member_geography_id"],
            payload["group_geography_id"],
            payload["start_date"],
        )
        existing = existing_by_key.get(key)
        if existing is None:
            membership_row = GeographyMembership(**payload)
            session.add(membership_row)
            existing_by_key[key] = membership_row
            outcome.inserted += 1
            continue
        if assign_if_changed(existing, payload, updatable_fields):
            outcome.updated += 1

    await session.flush()
    return outcome


__all__ = ["seed_geography_memberships"]
