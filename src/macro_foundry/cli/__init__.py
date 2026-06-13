"""Typer CLI entry point.

The package is structured by command surface so each subcommand has a
focused module. Importing this package registers every command on the
root Typer app.
"""

from __future__ import annotations

from ._app import app, db_app, embeddings_app, serve_app

# Import subcommand modules for their decorator side effects.
from . import db, embeddings, seed, serve  # noqa: F401  (side-effect imports)

# `onboard` still wires the retired `macro_foundry.agent` package (ADR 0023) and
# is pending rewrite under `onboarding_agent`. Until then its missing imports must
# not take down the rest of the CLI — notably `serve mcp`, which `langgraph dev`
# spawns as the macrodb-mcp server.
try:
    from . import onboard  # noqa: F401  (side-effect import)
except ModuleNotFoundError:
    pass

__all__ = ["app", "db_app", "embeddings_app", "serve_app"]
