"""Generic JSON-path extraction selector."""

from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from macro_foundry.enums import Frequency
from macro_foundry.ingestion.runtime.calendar import period_bounds
from macro_foundry.ingestion.runtime.types import ExtractionResult, ParsedObservation, ValidationResult


class JsonPathSelector:
    """Extract observations from a JSON payload using simple field paths."""

    name = "json_path"
    config_schema: dict[str, Any] = {
        "type": "object",
        "required": ["records_path", "period_anchor_field", "value_field", "frequency"],
        "properties": {
            "records_path": {"type": "string"},
            "period_anchor_field": {"type": "string"},
            "value_field": {"type": "string"},
            "frequency": {"type": "string"},
            "missing_value_tokens": {"type": "array", "items": {"type": "string"}},
            "snapshot_vintage_date": {"type": "string", "format": "date"},
            "vintage_date_field": {"type": "string"},
        },
    }

    def validate(self, config: dict[str, Any]) -> ValidationResult:
        errors: list[str] = []
        for key in ("records_path", "period_anchor_field", "value_field", "frequency"):
            if not config.get(key):
                errors.append(f"{key} is required")
        try:
            Frequency(str(config.get("frequency")))
        except ValueError:
            errors.append("frequency must be a known Frequency value")
        if config.get("snapshot_vintage_date") and config.get("vintage_date_field"):
            errors.append("snapshot_vintage_date and vintage_date_field are mutually exclusive")
        return ValidationResult(is_valid=not errors, errors=tuple(errors))

    def extract(self, payload: Any, config: dict[str, Any]) -> ExtractionResult:
        validation = self.validate(config)
        if not validation.is_valid:
            raise ValueError("; ".join(validation.errors))

        provider_error = _parse_provider_error(payload)
        if provider_error is not None:
            return ExtractionResult(
                outcome="provider_error",
                observations=[],
                error_message=provider_error,
            )

        records = _resolve_path(payload, str(config["records_path"]))
        if records is None:
            records = []
        if not isinstance(records, list):
            raise ValueError("records_path must resolve to a JSON array")

        frequency = Frequency(str(config["frequency"]))
        missing_tokens = {str(token) for token in config.get("missing_value_tokens", [])}
        snapshot_vintage_date = _parse_optional_date(config.get("snapshot_vintage_date"))
        observations: list[ParsedObservation] = []

        for record in records:
            if not isinstance(record, dict):
                raise ValueError("records_path must contain JSON objects")
            anchor = date.fromisoformat(str(_resolve_path(record, str(config["period_anchor_field"]))))
            period_start, period_end = period_bounds(anchor, frequency)
            value = _parse_optional_decimal(
                _resolve_path(record, str(config["value_field"])),
                missing_tokens=missing_tokens,
            )
            vintage_date = snapshot_vintage_date
            vintage_field = config.get("vintage_date_field")
            if vintage_field:
                vintage_date = _parse_optional_date(_resolve_path(record, str(vintage_field)))
            observations.append(
                ParsedObservation(
                    period_start=period_start,
                    period_end=period_end,
                    value=value,
                    vintage_date=vintage_date,
                ),
            )

        if not observations:
            return ExtractionResult(outcome="empty", observations=[])
        return ExtractionResult(outcome="data", observations=observations)


def _resolve_path(payload: Any, path: str) -> Any:
    value = payload
    for part in path.split("."):
        if isinstance(value, dict):
            value = value.get(part)
            continue
        return None
    return value


def _parse_optional_date(raw_value: Any) -> date | None:
    if raw_value in (None, ""):
        return None
    return date.fromisoformat(str(raw_value))


def _parse_optional_decimal(raw_value: Any, *, missing_tokens: set[str]) -> Decimal | None:
    if raw_value is None or str(raw_value) in missing_tokens:
        return None
    try:
        return Decimal(str(raw_value))
    except InvalidOperation as exc:
        raise ValueError(f"Invalid numeric value {raw_value!r}") from exc


def _parse_provider_error(payload: Any) -> str | None:
    if not isinstance(payload, dict):
        return None
    for key in ("Information", "Note", "Error Message", "error_message"):
        if payload.get(key):
            return str(payload[key])
    if payload.get("error_code"):
        message = payload.get("error_message", "unknown error")
        return f"provider error {payload['error_code']}: {message}"
    return None


__all__ = ["JsonPathSelector"]
