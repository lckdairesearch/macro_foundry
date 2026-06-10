"""Public types for the generic ingestion runtime."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any, Literal, NamedTuple, Protocol


class ParsedObservation(NamedTuple):
    """Normalized observation emitted by a selector."""

    period_start: date
    period_end: date
    value: Decimal | None
    vintage_date: date | None


@dataclass(frozen=True, slots=True)
class ValidationResult:
    """Static selector-config validation result."""

    is_valid: bool
    errors: tuple[str, ...] = ()


ExtractionOutcome = Literal["data", "empty", "provider_error"]


@dataclass(frozen=True, slots=True)
class ExtractionResult:
    """Result of parsing a provider payload."""

    outcome: ExtractionOutcome
    observations: list[ParsedObservation]
    error_message: str | None = None
    diagnostics: dict[str, Any] | None = None


class Selector(Protocol):
    """Selector contract implemented by runtime selector types."""

    name: str
    config_schema: dict[str, Any]

    def validate(self, config: dict[str, Any]) -> ValidationResult:
        """Validate static selector configuration."""

    def extract(self, payload: Any, config: dict[str, Any]) -> ExtractionResult:
        """Extract normalized observations from a provider payload."""


__all__ = [
    "ExtractionOutcome",
    "ExtractionResult",
    "ParsedObservation",
    "Selector",
    "ValidationResult",
]
