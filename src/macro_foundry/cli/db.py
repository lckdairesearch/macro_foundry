"""`macrodb db …` subcommands."""

from __future__ import annotations

import asyncio
from typing import Annotated

import typer

from macro_foundry.db import EnvTarget

from . import _helpers
from ._app import db_app

_DEV_OR_TEST = {EnvTarget.DEV, EnvTarget.TEST}

bootstrap_app = typer.Typer(help="Curated bootstrap/import commands.")
db_app.add_typer(bootstrap_app, name="bootstrap")


@bootstrap_app.command("fred-us-macro")
@_helpers.cli_error_handler
def bootstrap_fred_us_macro(
    target: Annotated[
        EnvTarget,
        typer.Option("--target", case_sensitive=False, help="Target dev or test database."),
    ] = EnvTarget.DEV,
    reset: Annotated[
        bool,
        typer.Option("--reset", help="Delete the curated FRED preset rows instead of bootstrapping them."),
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
    """Bootstrap the curated first-pass FRED U.S. macro preset."""

    if target not in _DEV_OR_TEST:
        typer.echo(f"db bootstrap does not support --target {target.value} (allowed: dev, test)", err=True)
        raise typer.Exit(code=2)

    if reset:
        _helpers.confirm_destructive(yes, "Delete all FRED preset rows?")

    summary = asyncio.run(
        _helpers._bootstrap_database(
            target=target,
            reset=reset,
            preset="fred-us-macro",
        ),
    )

    if reset:
        result = {
            "target": summary.database.value,
            "reset": "fred-us-macro",
            "observations_deleted": summary.observations_deleted,
            "ingestion_run_logs_deleted": summary.ingestion_run_logs_deleted,
            "computation_run_logs_deleted": summary.computation_run_logs_deleted,
            "derivation_inputs_deleted": summary.derivation_inputs_deleted,
            "derived_series_deleted": summary.derived_series_deleted,
            "ingestion_feeds_deleted": summary.ingestion_feeds_deleted,
            "series_sources_deleted": summary.series_sources_deleted,
            "family_members_deleted": summary.family_members_deleted,
            "series_deleted": summary.series_deleted,
            "families_deleted": summary.families_deleted,
            "concepts_deleted": summary.concepts_deleted,
        }
        _helpers.print_result(result, as_json=output_json)
        return

    result = {
        "target": summary.database.value,
        "run_date": summary.run_date.isoformat(),
    }
    _helpers.print_result(result, as_json=output_json)
    for r in summary.raw_imports:
        typer.echo(f"raw {r.series_code}: fetched={r.rows_fetched} written={r.rows_written} skipped={r.rows_skipped}")
    for r in summary.derived_imports:
        typer.echo(f"derived {r.series_code}: computed={r.rows_computed} written={r.rows_written} skipped={r.rows_skipped}")


@bootstrap_app.command("debug-smoke")
@_helpers.cli_error_handler
def bootstrap_debug_smoke(
    target: Annotated[
        EnvTarget,
        typer.Option("--target", case_sensitive=False, help="Target dev or test database."),
    ] = EnvTarget.DEV,
    output_json: Annotated[
        bool,
        typer.Option("--json", help="Emit results as JSON instead of key=value lines."),
    ] = False,
) -> None:
    """Bootstrap a minimal request-centric ingestion and hierarchy debug set."""

    if target not in _DEV_OR_TEST:
        typer.echo(f"db bootstrap does not support --target {target.value} (allowed: dev, test)", err=True)
        raise typer.Exit(code=2)

    summary = asyncio.run(
        _helpers._bootstrap_database(
            target=target,
            reset=False,
            preset="debug-smoke",
        ),
    )

    result = {
        "target": summary.database.value,
        "run_date": summary.run_date.isoformat(),
        "preset": "debug-smoke",
        "request_feed_members": summary.feed_members,
        "member_logs": summary.member_logs,
        "observations": summary.observations,
        "hierarchy_edges": summary.hierarchy_edges,
    }
    _helpers.print_result(result, as_json=output_json)
