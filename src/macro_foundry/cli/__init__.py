"""Typer CLI entry point.

The package is structured by command surface so each subcommand has a
focused module. Importing this package registers every command on the
root Typer app.
"""

from __future__ import annotations

from ._app import app, db_app, serve_app

# Import subcommand modules for their decorator side effects.
from . import db, onboard, seed, serve  # noqa: F401  (side-effect imports)

__all__ = ["app", "db_app", "serve_app"]
