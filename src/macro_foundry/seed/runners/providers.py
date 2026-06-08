"""Provider and provider-catalog seed runners."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from macro_foundry.models import Provider, ProviderCatalog
from macro_foundry.schemas import ProviderCatalogCreate, ProviderCreate
from macro_foundry.seed._shared import SeedOutcome, assign_if_changed
from macro_foundry.seed.data.providers import PROVIDER_CATALOGS, PROVIDERS


async def seed_providers(session: AsyncSession) -> SeedOutcome:
    """Seed default providers."""

    payloads = [ProviderCreate(**provider).model_dump() for provider in PROVIDERS]
    provider_names = [provider["name"] for provider in PROVIDERS]
    existing_names = set((await session.execute(select(Provider.name).where(Provider.name.in_(provider_names)))).scalars())

    statement = insert(Provider).values(payloads)
    statement = statement.on_conflict_do_update(
        index_elements=[Provider.name],
        set_={
            "alt_name": statement.excluded.alt_name,
            "type": statement.excluded.type,
            "homepage_url": statement.excluded.homepage_url,
            "doc_url": statement.excluded.doc_url,
            "base_url": statement.excluded.base_url,
            "credentials_ref": statement.excluded.credentials_ref,
            "notes": statement.excluded.notes,
            "is_active": statement.excluded.is_active,
            "updated_at": func.now(),
        },
    )
    await session.execute(statement)
    await session.flush()
    return SeedOutcome(
        inserted=len(provider_names) - len(existing_names),
        updated=len(existing_names),
    )


async def seed_provider_catalogs(session: AsyncSession) -> SeedOutcome:
    """Seed default provider catalogs using natural-key reconciliation."""

    provider_names = [catalog["provider_name"] for catalog in PROVIDER_CATALOGS]
    provider_rows = await session.execute(
        select(Provider.name, Provider.id).where(Provider.name.in_(provider_names)),
    )
    provider_ids = {name: provider_id for name, provider_id in provider_rows}

    missing_providers = sorted(set(provider_names) - set(provider_ids))
    if missing_providers:
        raise ValueError(f"Provider catalog seed references unknown providers: {missing_providers}")

    catalogs = (
        await session.execute(
            select(ProviderCatalog).where(ProviderCatalog.provider_id.in_(tuple(provider_ids.values()))),
        )
    ).scalars()

    existing_by_key: dict[tuple[object, str], ProviderCatalog] = {}
    for catalog in catalogs:
        key = (catalog.provider_id, catalog.name)
        if key in existing_by_key:
            raise ValueError(f"Duplicate provider catalog rows found for provider_id={catalog.provider_id} name={catalog.name!r}")
        existing_by_key[key] = catalog

    outcome = SeedOutcome()
    updatable_fields = ("catalog_url", "doc_url", "notes", "is_placeholder")

    for catalog in PROVIDER_CATALOGS:
        payload = ProviderCatalogCreate(
            provider_id=provider_ids[catalog["provider_name"]],
            name=catalog["name"],
            catalog_url=catalog.get("catalog_url"),
            doc_url=catalog.get("doc_url"),
            notes=catalog.get("notes"),
            is_placeholder=catalog["is_placeholder"],
        ).model_dump()
        key = (payload["provider_id"], payload["name"])
        existing = existing_by_key.get(key)
        if existing is None:
            catalog_row = ProviderCatalog(**payload)
            session.add(catalog_row)
            existing_by_key[key] = catalog_row
            outcome.inserted += 1
            continue
        if assign_if_changed(existing, payload, updatable_fields):
            outcome.updated += 1

    await session.flush()
    return outcome


__all__ = ["seed_provider_catalogs", "seed_providers"]
