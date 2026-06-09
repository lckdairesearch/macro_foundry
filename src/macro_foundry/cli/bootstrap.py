"""`macrodb bootstrap …` subcommands."""

from __future__ import annotations

import asyncio

import typer

from macro_foundry.bootstrap import DatabaseTarget

from . import _helpers
from ._app import bootstrap_app


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
            _helpers._bootstrap_database(
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
            _helpers._bootstrap_database(
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
