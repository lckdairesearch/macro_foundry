"""Provider-specific ingestion adapters."""

from macro_foundry.ingestion.providers.fred import (
    FredClient,
    FredClientProtocol,
    FredObservation,
    FredSeriesMetadata,
    fred_period_bounds,
)

__all__ = [
    "FredClient",
    "FredClientProtocol",
    "FredObservation",
    "FredSeriesMetadata",
    "fred_period_bounds",
]
