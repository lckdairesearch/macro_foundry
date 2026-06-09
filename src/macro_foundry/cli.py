"""Typer CLI entry point."""

from __future__ import annotations

import asyncio

import typer
import uvicorn

from macro_foundry.bootstrap import BootstrapDatabaseTarget, run_fred_us_macro_bootstrap
from macro_foundry.db import AsyncSessionLocal
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
    reload: bool = typer.Option(
        default=True,
        help="Enable auto-reload for local development.",
    ),
) -> None:
    """Start the FastAPI application with development defaults."""

    uvicorn.run(
        "macro_foundry.backend.main:app",
        host=host,
        port=port,
        reload=reload,
    )


@bootstrap_app.command("fred-us-macro")
def bootstrap_fred_us_macro(
    database: BootstrapDatabaseTarget = typer.Option(
        default=BootstrapDatabaseTarget.APP,
        case_sensitive=False,
        help="Target the app or test database.",
    ),
) -> None:
    """Bootstrap the curated first-pass FRED U.S. macro preset."""

    try:
        summary = asyncio.run(run_fred_us_macro_bootstrap(database=database))
    except ValueError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc

    typer.echo(f"database={summary.database.value} run_date={summary.run_date.isoformat()}")
    for result in summary.raw_imports:
        typer.echo(
            f"raw {result.series_code}: fetched={result.rows_fetched} written={result.rows_written} skipped={result.rows_skipped}",
        )
    for result in summary.derived_imports:
        typer.echo(
            f"derived {result.series_code}: computed={result.rows_computed} written={result.rows_written} skipped={result.rows_skipped}",
        )


__all__ = ["app", "bootstrap_fred_us_macro", "seed", "serve"]
