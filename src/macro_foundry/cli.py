"""Typer CLI entry point."""

from __future__ import annotations

import asyncio

import typer
import uvicorn

from macro_foundry.bootstrap import (
    DatabaseTarget,
    reset_fred_us_macro_bootstrap,
    run_debug_smoke_bootstrap,
    run_fred_us_macro_bootstrap,
)
from macro_foundry.db import AsyncSessionLocal, database_url_for_target
from macro_foundry.seed import parse_seed_targets, reset_seed_tables, run_seed


app = typer.Typer(help="macrodb command-line interface.")
bootstrap_app = typer.Typer(help="Curated bootstrap/import commands.")
app.add_typer(bootstrap_app, name="bootstrap")


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


@app.command("seed")
def seed(
    only: list[str] | None = typer.Option(
        default=None,
        help="Repeat to restrict seeding to one or more targets.",
    ),
    dry_run: bool = typer.Option(
        default=False,
        help="Prepare the seed changes and roll them back instead of committing.",
    ),
    reset: bool = typer.Option(
        default=False,
        help="Delete the seed-managed rows before reseeding.",
    ),
    confirm: bool = typer.Option(
        default=False,
        help="Required with --reset because the reset path is destructive.",
    ),
) -> None:
    """Seed the configured macrodb database."""

    if reset and not confirm:
        raise typer.BadParameter("--reset requires --confirm")

    try:
        summary = asyncio.run(
            _seed_database(
                only=only,
                dry_run=dry_run,
                reset=reset,
            ),
        )
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc

    for target, outcome in summary.items():
        typer.echo(
            f"{target.value}: inserted={outcome.inserted} updated={outcome.updated}",
        )
    if dry_run:
        typer.echo("dry-run: rolled back changes")


@app.command("serve")
def serve(
    host: str = typer.Option(
        default="127.0.0.1",
        help="Host interface to bind the API server to.",
    ),
    port: int = typer.Option(
        default=8000,
        min=1,
        max=65535,
        help="Port to bind the API server to.",
    ),
    database: DatabaseTarget = typer.Option(
        default=DatabaseTarget.APP,
        case_sensitive=False,
        help="Target the app or test database.",
    ),
    reload: bool = typer.Option(
        default=True,
        help="Enable auto-reload for local development.",
    ),
) -> None:
    """Start the FastAPI application with development defaults."""

    if database is DatabaseTarget.APP:
        uvicorn.run(
            "macro_foundry.backend.main:app",
            host=host,
            port=port,
            reload=reload,
        )
        return

    from macro_foundry.backend.main import create_app

    uvicorn.run(
        create_app(database_url=database_url_for_target(database)),
        host=host,
        port=port,
        reload=False,
    )


@bootstrap_app.command("fred-us-macro")
def bootstrap_fred_us_macro(
    database: DatabaseTarget = typer.Option(
        default=DatabaseTarget.APP,
        case_sensitive=False,
        help="Target the app or test database.",
    ),
    reset: bool = typer.Option(
        default=False,
        help="Delete the curated FRED preset rows instead of bootstrapping them.",
    ),
    confirm: bool = typer.Option(
        default=False,
        help="Required with --reset because the reset path is destructive.",
    ),
) -> None:
    """Bootstrap the curated first-pass FRED U.S. macro preset."""

    if reset and not confirm:
        raise typer.BadParameter("--reset requires --confirm")

    try:
        summary = asyncio.run(
            _bootstrap_database(
                database=database,
                reset=reset,
                preset="fred-us-macro",
            ),
        )
    except ValueError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc

    if reset:
        typer.echo(f"database={summary.database.value} reset=fred-us-macro")
        typer.echo(
            "deleted "
            f"observations={summary.observations_deleted} "
            f"ingestion_run_logs={summary.ingestion_run_logs_deleted} "
            f"computation_run_logs={summary.computation_run_logs_deleted} "
            f"derivation_inputs={summary.derivation_inputs_deleted} "
            f"derived_series={summary.derived_series_deleted} "
            f"ingestion_feeds={summary.ingestion_feeds_deleted} "
            f"series_sources={summary.series_sources_deleted} "
            f"family_members={summary.family_members_deleted} "
            f"series={summary.series_deleted} "
            f"families={summary.families_deleted} "
            f"concepts={summary.concepts_deleted}",
        )
        return

    typer.echo(f"database={summary.database.value} run_date={summary.run_date.isoformat()}")
    for result in summary.raw_imports:
        typer.echo(
            f"raw {result.series_code}: fetched={result.rows_fetched} written={result.rows_written} skipped={result.rows_skipped}",
        )
    for result in summary.derived_imports:
        typer.echo(
            f"derived {result.series_code}: computed={result.rows_computed} written={result.rows_written} skipped={result.rows_skipped}",
        )


@bootstrap_app.command("debug-smoke")
def bootstrap_debug_smoke(
    database: DatabaseTarget = typer.Option(
        default=DatabaseTarget.APP,
        case_sensitive=False,
        help="Target the app or test database.",
    ),
) -> None:
    """Bootstrap a minimal request-centric ingestion and hierarchy debug set."""

    try:
        summary = asyncio.run(
            _bootstrap_database(
                database=database,
                reset=False,
                preset="debug-smoke",
            ),
        )
    except ValueError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc

    typer.echo(f"database={summary.database.value} run_date={summary.run_date.isoformat()} preset=debug-smoke")
    typer.echo(
        "request_feed_members="
        f"{summary.feed_members} member_logs={summary.member_logs} "
        f"observations={summary.observations} hierarchy_edges={summary.hierarchy_edges}",
    )


__all__ = ["app", "bootstrap_debug_smoke", "bootstrap_fred_us_macro", "seed", "serve"]
