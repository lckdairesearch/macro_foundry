"""Root Typer applications for the macrodb CLI."""

from __future__ import annotations

import typer

app = typer.Typer(help="macrodb command-line interface.")
bootstrap_app = typer.Typer(help="Curated bootstrap/import commands.")
app.add_typer(bootstrap_app, name="bootstrap")
