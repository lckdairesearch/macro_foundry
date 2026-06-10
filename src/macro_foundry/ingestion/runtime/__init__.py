"""Generic selector-registry ingestion runtime."""

from macro_foundry.ingestion.runtime.runner import FeedExecutionOutcome, execute_feed
from macro_foundry.ingestion.runtime.types import ExtractionResult, ParsedObservation, ValidationResult

__all__ = [
    "ExtractionResult",
    "FeedExecutionOutcome",
    "ParsedObservation",
    "ValidationResult",
    "execute_feed",
]
