"""CSV-column extraction selector."""

from __future__ import annotations

import csv
from datetime import date
from decimal import Decimal, InvalidOperation
from io import StringIO
from typing import Any

from macro_foundry.enums import Frequency
from macro_foundry.ingestion.runtime.calendar import period_bounds
from macro_foundry.ingestion.runtime.types import (
    ExtractionResult,
    ParsedObservation,
    ValidationResult,
)


class CsvColumnSelector:
    """Extract observations from CSV text by named columns."""

    name = "csv_column"
    config_schema: dict[str, Any] = {
        "type": "object",
        "required": ["period_column", "value_column", "frequency"],
        "properties": {
            "period_column": {"type": "string"},
            "value_column": {"type": "string"},
            "frequency": {"type": "string"},
            "delimiter": {"type": "string"},
            "missing_value_tokens": {"type": "array", "items": {"type": "string"}},
            "snapshot_vintage_date": {"type": "string", "format": "date"},
            "vintage_date_column": {"type": "string"},
        },
    }

    def validate(self, config: dict[str, Any]) -> ValidationResult:
        errors: list[str] = []
        for key in ("period_column", "value_column", "frequency"):
            if not config.get(key):
                errors.append(f"{key} is required")
        try:
            Frequency(str(config.get("frequency")))
        except ValueError:
            errors.append("frequency must be a known Frequency value")
        delimiter = config.get("delimiter", ",")
        if not isinstance(delimiter, str) or len(delimiter) != 1:
            errors.append("delimiter must be a single character")
        if config.get("snapshot_vintage_date") and config.get("vintage_date_column"):
            errors.append(
                "snapshot_vintage_date and vintage_date_column are mutually exclusive"
            )
        return ValidationResult(is_valid=not errors, errors=tuple(errors))

    def extract(self, payload: Any, config: dict[str, Any]) -> ExtractionResult:
        validation = self.validate(config)
        if not validation.is_valid:
            raise ValueError("; ".join(validation.errors))
        if not isinstance(payload, str):
            raise ValueError("csv_column payload must be CSV text")

        reader = csv.DictReader(
            StringIO(payload.lstrip("\ufeff")),
            delimiter=str(config.get("delimiter", ",")),
        )
        if reader.fieldnames and {"error_code", "error_message"}.issubset(
            set(reader.fieldnames)
        ):
            row = next(reader, None)
            if row is not None:
                return ExtractionResult(
                    outcome="provider_error",
                    observations=[],
                    error_message=f"provider error {row['error_code']}: {row['error_message']}",
                )
        missing_tokens = {
            str(token) for token in config.get("missing_value_tokens", [])
        }
        frequency = Frequency(str(config["frequency"]))
        snapshot_vintage_date = _parse_optional_date(
            config.get("snapshot_vintage_date")
        )
        observations: list[ParsedObservation] = []

        for row in reader:
            if not any(value not in (None, "") for value in row.values()):
                continue
            anchor = date.fromisoformat(str(row.get(str(config["period_column"]))))
            period_start, period_end = period_bounds(anchor, frequency)
            vintage_date = snapshot_vintage_date
            vintage_column = config.get("vintage_date_column")
            if vintage_column:
                vintage_date = _parse_optional_date(row.get(str(vintage_column)))
            observations.append(
                ParsedObservation(
                    period_start=period_start,
                    period_end=period_end,
                    value=_parse_optional_decimal(
                        row.get(str(config["value_column"])),
                        missing_tokens=missing_tokens,
                    ),
                    vintage_date=vintage_date,
                ),
            )

        if not observations:
            return ExtractionResult(outcome="empty", observations=[])
        return ExtractionResult(outcome="data", observations=observations)


def _parse_optional_date(raw_value: Any) -> date | None:
    if raw_value in (None, ""):
        return None
    return date.fromisoformat(str(raw_value))


def _parse_optional_decimal(
    raw_value: Any, *, missing_tokens: set[str]
) -> Decimal | None:
    if raw_value is None or str(raw_value) in missing_tokens:
        return None
    try:
        return Decimal(str(raw_value))
    except InvalidOperation as exc:
        raise ValueError(f"Invalid numeric value {raw_value!r}") from exc


__all__ = ["CsvColumnSelector"]
