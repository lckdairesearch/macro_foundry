"""`macrodb seed` command."""

from __future__ import annotations

import asyncio

import typer

from . import _helpers
from ._app import app


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
            _helpers._seed_database(
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
