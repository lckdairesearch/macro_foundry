"""Japan e-Stat value-dimension extraction selector."""

from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from macro_foundry.enums import Frequency
from macro_foundry.ingestion.runtime.calendar import period_bounds
from macro_foundry.ingestion.runtime.types import (
    ExtractionResult,
    ParsedObservation,
    ValidationResult,
)


class EstatValueFilterSelector:
    """Extract e-Stat VALUE rows matching configured dimension values."""

    name = "estat_value_filter"
    config_schema: dict[str, Any] = {
        "type": "object",
        "required": [
            "values_path",
            "value_dimension_filter",
            "time_field",
            "value_field",
            "frequency",
        ],
        "properties": {
            "values_path": {"type": "string"},
            "value_dimension_filter": {"type": "object"},
            "time_field": {"type": "string"},
            "value_field": {"type": "string"},
            "frequency": {"type": "string"},
            "missing_value_tokens": {"type": "array", "items": {"type": "string"}},
            "snapshot_vintage_date": {"type": "string", "format": "date"},
        },
    }

    def validate(self, config: dict[str, Any]) -> ValidationResult:
        errors: list[str] = []
        for key in (
            "values_path",
            "value_dimension_filter",
            "time_field",
            "value_field",
            "frequency",
        ):
            if not config.get(key):
                errors.append(f"{key} is required")
        if config.get("value_dimension_filter") and not isinstance(
            config["value_dimension_filter"], dict
        ):
            errors.append("value_dimension_filter must be an object")
        try:
            Frequency(str(config.get("frequency")))
        except ValueError:
            errors.append("frequency must be a known Frequency value")
        return ValidationResult(is_valid=not errors, errors=tuple(errors))

    def extract(self, payload: Any, config: dict[str, Any]) -> ExtractionResult:
        validation = self.validate(config)
        if not validation.is_valid:
            raise ValueError("; ".join(validation.errors))

        provider_error = _parse_provider_error(payload)
        if provider_error is not None:
            return ExtractionResult(
                outcome="provider_error", observations=[], error_message=provider_error
            )

        values = _resolve_path(payload, str(config["values_path"]))
        if values is None:
            values = []
        if isinstance(values, dict):
            values = [values]
        if not isinstance(values, list):
            raise ValueError("values_path must resolve to a JSON array or object")

        filters = {
            str(key): str(value)
            for key, value in config["value_dimension_filter"].items()
        }
        frequency = Frequency(str(config["frequency"]))
        missing_tokens = {
            str(token) for token in config.get("missing_value_tokens", [])
        }
        snapshot_vintage_date = _parse_optional_date(
            config.get("snapshot_vintage_date")
        )
        observations: list[ParsedObservation] = []

        for value_row in values:
            if not isinstance(value_row, dict):
                raise ValueError("values_path must contain JSON objects")
            if any(
                str(value_row.get(key)) != expected for key, expected in filters.items()
            ):
                continue
            anchor = _parse_estat_time(value_row.get(str(config["time_field"])))
            period_start, period_end = period_bounds(anchor, frequency)
            observations.append(
                ParsedObservation(
                    period_start=period_start,
                    period_end=period_end,
                    value=_parse_optional_decimal(
                        value_row.get(str(config["value_field"])),
                        missing_tokens=missing_tokens,
                    ),
                    vintage_date=snapshot_vintage_date,
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


def _parse_estat_time(raw_value: Any) -> date:
    value = str(raw_value)
    if len(value) == 10 and value[4:6] == "00":
        return date(int(value[0:4]), int(value[6:8]), 1)
    if len(value) == 10:
        return date(int(value[0:4]), int(value[4:6]), int(value[6:8]))
    return date.fromisoformat(value)


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
        return Decimal(str(raw_value).replace(",", ""))
    except InvalidOperation as exc:
        raise ValueError(f"Invalid numeric value {raw_value!r}") from exc


def _parse_provider_error(payload: Any) -> str | None:
    if not isinstance(payload, dict):
        return None
    result = _resolve_path(payload, "GET_STATS_DATA.RESULT")
    if isinstance(result, dict) and str(result.get("STATUS", "0")) != "0":
        status = result.get("STATUS")
        message = result.get("ERROR_MSG") or result.get("MESSAGE") or "unknown error"
        return f"provider error {status}: {message}"
    return None


__all__ = ["EstatValueFilterSelector"]
