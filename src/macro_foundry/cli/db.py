"""`macrodb db …` subcommands."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Annotated

import typer
from alembic import command as alembic_command
from alembic.config import Config as AlembicConfig
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine

from macro_foundry.db import EnvTarget, owner_url_for_target

from . import _helpers
from ._app import db_app

_DEV_OR_TEST = {EnvTarget.DEV, EnvTarget.TEST}
_ALEMBIC_INI = Path(__file__).resolve().parents[3] / "alembic.ini"


def _alembic_config_for(url: str) -> AlembicConfig:
    config = AlembicConfig(str(_ALEMBIC_INI))
    config.set_main_option("sqlalchemy.url", url)
    return config


def _current_revision(url: str) -> str | None:
    engine = create_engine(url, poolclass=None)
    try:
        with engine.connect() as connection:
            return MigrationContext.configure(connection).get_current_revision()
    finally:
        engine.dispose()


bootstrap_app = typer.Typer(help="Curated bootstrap/import commands.")
db_app.add_typer(bootstrap_app, name="bootstrap")


@db_app.command("migrate")
@_helpers.cli_error_handler
def migrate(
    target: Annotated[
        EnvTarget,
        typer.Option("--target", case_sensitive=False, help="Target dev or test database."),
    ] = EnvTarget.DEV,
    revision: Annotated[
        str,
        typer.Option("--revision", help="Alembic revision identifier (default: head)."),
    ] = "head",
    downgrade: Annotated[
        bool,
        typer.Option("--downgrade", help="Downgrade to --revision instead of upgrading."),
    ] = False,
    output_json: Annotated[
        bool,
        typer.Option("--json", help="Emit results as JSON instead of key=value lines."),
    ] = False,
) -> None:
    """Run Alembic migrations against the selected database as macrodb_owner."""

    if target not in _DEV_OR_TEST:
        typer.echo(f"db migrate does not support --target {target.value} (allowed: dev, test)", err=True)
        raise typer.Exit(code=2)

    url = owner_url_for_target(target)
    config = _alembic_config_for(url)

    before = _current_revision(url)
    if downgrade:
        alembic_command.downgrade(config, revision)
    else:
        alembic_command.upgrade(config, revision)
    after = _current_revision(url)

    _helpers.print_result(
        {
            "target": target.value,
            "direction": "downgrade" if downgrade else "upgrade",
            "revision": revision,
            "before": before or "base",
            "after": after or "base",
        },
        as_json=output_json,
    )


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
            "target": summary.target.value,
            "reset": "fred-us-macro",
            "observations_deleted": summary.observations_deleted,
            "ingestion_run_logs_deleted": summary.ingestion_run_logs_deleted,
            "ingestion_feeds_deleted": summary.ingestion_feeds_deleted,
            "series_sources_deleted": summary.series_sources_deleted,
            "indicator_variants_deleted": summary.indicator_variants_deleted,
            "series_deleted": summary.series_deleted,
            "indicators_deleted": summary.indicators_deleted,
            "concepts_deleted": summary.concepts_deleted,
        }
        _helpers.print_result(result, as_json=output_json)
        return

    result = {
        "target": summary.target.value,
        "run_date": summary.run_date.isoformat(),
    }
    _helpers.print_result(result, as_json=output_json)
    for r in summary.raw_imports:
        typer.echo(f"raw {r.series_code}: fetched={r.rows_fetched} written={r.rows_written} skipped={r.rows_skipped}")


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
        "target": summary.target.value,
        "run_date": summary.run_date.isoformat(),
        "preset": "debug-smoke",
        "request_feed_members": summary.feed_members,
        "member_logs": summary.member_logs,
        "observations": summary.observations,
        "hierarchy_edges": summary.hierarchy_edges,
    }
    _helpers.print_result(result, as_json=output_json)
