"""Curated first-pass FRED U.S. macro bootstrap — disabled pending V8 rebootstrap.

The original bootstrap materialized the V7 conceptual spine
(concept -> indicator -> indicator_variant -> series) that ADR 0025 dropped.
Rebuilding the curated FRED preset against the `categories` tree is the V8
rebootstrap slice; until then the public entrypoints are intentionally inert.
The previous implementation (including the curated `RAW_SERIES_SPECS`) is
preserved in git history for that slice to draw from.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from macro_foundry.db import EnvTarget

_DEFERRED_MESSAGE = (
    "The curated FRED U.S. macro bootstrap is disabled pending the V8 rebootstrap "
    "slice (ADR 0025): it built the dropped concept/indicator/variant spine."
)


@dataclass(frozen=True, slots=True)
class FredUsMacroBootstrapResult:
    """End-to-end bootstrap summary returned to the CLI and tests."""

    target: EnvTarget
    run_date: date
    raw_imports: tuple[Any, ...]


@dataclass(frozen=True, slots=True)
class FredUsMacroResetResult:
    """Summary of removing the curated first-pass FRED preset."""

    target: EnvTarget
    observations_deleted: int
    ingestion_run_logs_deleted: int
    ingestion_feeds_deleted: int
    series_sources_deleted: int
    series_deleted: int


async def run_fred_us_macro_bootstrap(*args: Any, **kwargs: Any) -> FredUsMacroBootstrapResult:
    raise NotImplementedError(_DEFERRED_MESSAGE)


async def reset_fred_us_macro_bootstrap(*args: Any, **kwargs: Any) -> FredUsMacroResetResult:
    raise NotImplementedError(_DEFERRED_MESSAGE)


__all__ = [
    "EnvTarget",
    "FredUsMacroBootstrapResult",
    "FredUsMacroResetResult",
    "reset_fred_us_macro_bootstrap",
    "run_fred_us_macro_bootstrap",
]
