"""Tag seed runner."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from macro_foundry.models import Tag
from macro_foundry.schemas import TagCreate
from macro_foundry.seed._shared import SeedOutcome
from macro_foundry.seed.data.tags import TAGS


async def seed_tags(session: AsyncSession) -> SeedOutcome:
    """Seed the topical tag taxonomy, upserting on the `code` key."""

    payloads = [TagCreate(code=code, name=name).model_dump() for code, name in TAGS]
    codes = [code for code, _name in TAGS]
    existing_codes = set((await session.execute(select(Tag.code).where(Tag.code.in_(codes)))).scalars())

    statement = insert(Tag).values(payloads)
    statement = statement.on_conflict_do_update(
        index_elements=[Tag.code],
        set_={"name": statement.excluded.name, "updated_at": func.now()},
    )
    await session.execute(statement)
    await session.flush()
    return SeedOutcome(
        inserted=len(codes) - len(existing_codes),
        updated=len(existing_codes),
    )


__all__ = ["seed_tags"]
