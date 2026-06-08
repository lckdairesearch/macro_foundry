"""Typer CLI entry point."""

from __future__ import annotations

import asyncio

import typer
import uvicorn

from macro_foundry.db import AsyncSessionLocal
from macro_foundry.seed import parse_seed_targets, reset_seed_tables, run_seed


app = typer.Typer(help="macrodb command-line interface.")


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


__all__ = ["app", "seed", "serve"]
