"""Async helpers shared by CLI subcommands."""

from __future__ import annotations

from macro_foundry.bootstrap import (
    DatabaseTarget,
    reset_fred_us_macro_bootstrap,
    run_debug_smoke_bootstrap,
    run_fred_us_macro_bootstrap,
)
from macro_foundry.db import AsyncSessionLocal
from macro_foundry.seed import parse_seed_targets, reset_seed_tables, run_seed


async def _seed_database(
    *,
    only: list[str] | None,
    dry_run: bool,
    reset: bool,
) -> dict[object, object]:
    selected_targets = parse_seed_targets(only)

    async with AsyncSessionLocal() as session:
        try:
            if reset:
                await reset_seed_tables(session, only=selected_targets)
            summary = await run_seed(session, only=selected_targets)
            if dry_run:
                await session.rollback()
            else:
                await session.commit()
            return summary
        except Exception:
            await session.rollback()
            raise


async def _bootstrap_database(
    *,
    database: DatabaseTarget,
    reset: bool,
    preset: str,
) -> object:
    if preset == "debug-smoke":
        if reset:
            raise ValueError("debug-smoke does not support --reset")
        return await run_debug_smoke_bootstrap(database=database)
    if reset:
        return await reset_fred_us_macro_bootstrap(database=database)
    return await run_fred_us_macro_bootstrap(database=database)
