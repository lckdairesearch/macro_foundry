"""`macrodb seed` command."""

from __future__ import annotations

import asyncio
from typing import Annotated

import typer

from macro_foundry.db import EnvTarget

from . import _helpers
from ._app import app

_DEV_OR_TEST = {EnvTarget.DEV, EnvTarget.TEST}


@app.command("seed")
@_helpers.cli_error_handler
def seed(
    target: Annotated[
        EnvTarget,
        typer.Option("--target", case_sensitive=False, help="Target dev or test database."),
    ] = EnvTarget.DEV,
    only: Annotated[
        list[str] | None,
        typer.Option("--only", help="Repeat to restrict seeding to one or more targets."),
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Prepare the seed changes and roll them back instead of committing."),
    ] = False,
    reset: Annotated[
        bool,
        typer.Option("--reset", help="Delete the seed-managed rows before reseeding."),
    ] = False,
    yes: Annotated[
        bool,
        typer.Option("--yes", "-y", help="Skip the interactive confirmation prompt for destructive actions."),
    ] = False,
    output_json: Annotated[
        bool,
        typer.Option("--json", help="Emit results as JSON instead of key=value lines."),
    ] = False,
) -> None:
    """Seed the configured macrodb database."""

    if target not in _DEV_OR_TEST:
        typer.echo(f"seed does not support --target {target.value} (allowed: dev, test)", err=True)
        raise typer.Exit(code=2)

    if reset:
        _helpers.confirm_destructive(yes, "Delete seed-managed rows before reseeding?")

    summary = asyncio.run(
        _helpers._seed_database(
            target=target,
            only=only,
            dry_run=dry_run,
            reset=reset,
        ),
    )

    for seed_target, outcome in summary.items():
        typer.echo(
            f"{seed_target.value}: inserted={outcome.inserted} updated={outcome.updated}",
        )
    if dry_run:
        typer.echo("dry-run: rolled back changes")
