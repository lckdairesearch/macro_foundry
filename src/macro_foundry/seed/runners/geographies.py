"""Geography seed runner."""

from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from macro_foundry.enums import CodeStandard, GeographyType
from macro_foundry.models import Geography
from macro_foundry.schemas import GeographyCreate
from macro_foundry.seed._shared import SeedOutcome
from macro_foundry.seed.data.geographies import BLOCS, COUNTRIES, SUBNATIONALS, SUBNATIONAL_REGIONS, WORLD, GeographySeed


def _build_geography_payload(
    seed: GeographySeed,
    *,
    geography_type: GeographyType,
    parent_geography_id: object | None = None,
    default_code_standard: CodeStandard,
) -> dict[str, object]:
    payload = GeographyCreate(
        code=seed["code"],
        name=seed["name"],
        alt_name=seed.get("alt_name"),
        type=geography_type,
        code_standard=seed.get("code_standard", default_code_standard),
        parent_geography_id=parent_geography_id,
        notes=seed.get("notes"),
    )
    return payload.model_dump()


async def _load_geography_ids(session: AsyncSession, codes: Iterable[str]) -> dict[str, object]:
    rows = await session.execute(
        select(Geography.code, Geography.id).where(Geography.code.in_(tuple(codes))),
    )
    return {code: geography_id for code, geography_id in rows}


async def _upsert_geography_batch(session: AsyncSession, payloads: list[dict[str, object]]) -> SeedOutcome:
    if not payloads:
        return SeedOutcome()

    codes = [str(payload["code"]) for payload in payloads]
    existing_codes = set((await session.execute(select(Geography.code).where(Geography.code.in_(codes)))).scalars())

    statement = insert(Geography).values(payloads)
    statement = statement.on_conflict_do_update(
        index_elements=[Geography.code],
        set_={
            "name": statement.excluded.name,
            "alt_name": statement.excluded.alt_name,
            "type": statement.excluded.type,
            "code_standard": statement.excluded.code_standard,
            "parent_geography_id": statement.excluded.parent_geography_id,
            "notes": statement.excluded.notes,
            "updated_at": func.now(),
        },
    )
    await session.execute(statement)
    await session.flush()
    return SeedOutcome(
        inserted=len(codes) - len(existing_codes),
        updated=len(existing_codes),
    )


async def seed_geographies(session: AsyncSession) -> SeedOutcome:
    """Seed countries, blocs, world, and curated subnational geographies."""

    outcome = SeedOutcome()

    root_payloads = [
        *[
            _build_geography_payload(
                seed,
                geography_type=GeographyType.COUNTRY,
                default_code_standard=CodeStandard.ISO_3166_1,
            )
            for seed in COUNTRIES
        ],
        *[
            _build_geography_payload(
                seed,
                geography_type=GeographyType.BLOC,
                default_code_standard=CodeStandard.INTERNAL,
            )
            for seed in BLOCS
        ],
        _build_geography_payload(
            WORLD,
            geography_type=GeographyType.WORLD,
            default_code_standard=CodeStandard.WB,
        ),
    ]
    outcome.absorb(await _upsert_geography_batch(session, root_payloads))

    parent_codes = {
        *(seed["parent_code"] for seed in SUBNATIONALS),
        *(seed["parent_code"] for seed in SUBNATIONAL_REGIONS),
    }
    geography_ids = await _load_geography_ids(session, parent_codes)

    child_payloads = [
        *[
            _build_geography_payload(
                seed,
                geography_type=GeographyType.SUBNATIONAL,
                parent_geography_id=geography_ids[seed["parent_code"]],
                default_code_standard=CodeStandard.ISO_3166_2,
            )
            for seed in SUBNATIONALS
        ],
        *[
            _build_geography_payload(
                seed,
                geography_type=GeographyType.SUBNATIONAL_REGION,
                parent_geography_id=geography_ids[seed["parent_code"]],
                default_code_standard=CodeStandard.INTERNAL,
            )
            for seed in SUBNATIONAL_REGIONS
        ],
    ]
    outcome.absorb(await _upsert_geography_batch(session, child_payloads))
    return outcome


__all__ = ["seed_geographies"]
