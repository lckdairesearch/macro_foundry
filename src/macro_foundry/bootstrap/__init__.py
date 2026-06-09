"""Curated bootstrap entrypoints."""

from macro_foundry.bootstrap.fred_us_macro import (
    BootstrapDatabaseTarget,
    FredUsMacroBootstrapResult,
    run_fred_us_macro_bootstrap,
)

__all__ = [
    "BootstrapDatabaseTarget",
    "FredUsMacroBootstrapResult",
    "run_fred_us_macro_bootstrap",
]
