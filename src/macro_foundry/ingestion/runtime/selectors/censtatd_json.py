"""Hong Kong CenStatD JSON extraction selector."""

from __future__ import annotations

import json
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


class CenstatdJsonSelector:
    """Extract CenStatD observations using code-length hierarchy filtering."""

    name = "censtatd_json"
    config_schema: dict[str, Any] = {
        "type": "object",
        "required": [
            "records_path",
            "period_field",
            "value_field",
            "frequency",
            "hierarchy_code_field",
            "hierarchy_code_length",
        ],
        "properties": {
            "records_path": {"type": "string"},
            "period_field": {"type": "string"},
            "value_field": {"type": "string"},
            "frequency": {"type": "string"},
            "hierarchy_code_field": {"type": "string"},
            "hierarchy_code_length": {"type": "integer", "minimum": 1},
            "missing_value_tokens": {"type": "array", "items": {"type": "string"}},
            "snapshot_vintage_date": {"type": "string", "format": "date"},
            "static_params": {"type": "object"},
            "compressed_param_name": {"type": "string"},
            "compressed_params": {"type": "object"},
        },
    }

    def validate(self, config: dict[str, Any]) -> ValidationResult:
        errors: list[str] = []
        for key in (
            "records_path",
            "period_field",
            "value_field",
            "frequency",
            "hierarchy_code_field",
            "hierarchy_code_length",
        ):
            if not config.get(key):
                errors.append(f"{key} is required")
        try:
            Frequency(str(config.get("frequency")))
        except ValueError:
            errors.append("frequency must be a known Frequency value")
        if (
            config.get("hierarchy_code_length")
            and int(config["hierarchy_code_length"]) < 1
        ):
            errors.append("hierarchy_code_length must be positive")
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

        records = _resolve_path(payload, str(config["records_path"]))
        if records is None:
            records = []
        if not isinstance(records, list):
            raise ValueError("records_path must resolve to a JSON array")

        frequency = Frequency(str(config["frequency"]))
        code_field = str(config["hierarchy_code_field"])
        code_length = int(config["hierarchy_code_length"])
        missing_tokens = {
            str(token) for token in config.get("missing_value_tokens", [])
        }
        snapshot_vintage_date = _parse_optional_date(
            config.get("snapshot_vintage_date")
        )
        observations: list[ParsedObservation] = []

        for record in records:
            if not isinstance(record, dict):
                raise ValueError("records_path must contain JSON objects")
            if len(str(record.get(code_field, ""))) != code_length:
                continue
            anchor = _parse_period_anchor(record.get(str(config["period_field"])))
            period_start, period_end = period_bounds(anchor, frequency)
            observations.append(
                ParsedObservation(
                    period_start=period_start,
                    period_end=period_end,
                    value=_parse_optional_decimal(
                        record.get(str(config["value_field"])),
                        missing_tokens=missing_tokens,
                    ),
                    vintage_date=snapshot_vintage_date,
                ),
            )

        if not observations:
            return ExtractionResult(outcome="empty", observations=[])
        return ExtractionResult(outcome="data", observations=observations)

    def prepare_request_params(self, config: dict[str, Any]) -> dict[str, str]:
        """Return static params plus CenStatD's LZ-string-compressed query param."""

        params = {
            str(key): str(value)
            for key, value in (config.get("static_params") or {}).items()
        }
        compressed_params = config.get("compressed_params")
        compressed_param_name = config.get("compressed_param_name")
        if compressed_params is None:
            return params
        if not compressed_param_name:
            raise ValueError(
                "compressed_param_name is required when compressed_params is set"
            )
        raw_payload = json.dumps(
            compressed_params, separators=(",", ":"), sort_keys=True
        )
        params[str(compressed_param_name)] = _compress_to_encoded_uri_component(
            raw_payload
        )
        return params


def _resolve_path(payload: Any, path: str) -> Any:
    value = payload
    for part in path.split("."):
        if isinstance(value, dict):
            value = value.get(part)
            continue
        return None
    return value


def _parse_period_anchor(raw_value: Any) -> date:
    value = str(raw_value)
    if len(value) == 7 and value[4] == "-":
        return date.fromisoformat(f"{value}-01")
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
    if payload.get("errorCode"):
        return f"provider error {payload['errorCode']}: {payload.get('errorMessage', 'unknown error')}"
    if payload.get("error"):
        return str(payload["error"])
    return None


def _compress_to_encoded_uri_component(value: str) -> str:
    return _compress(
        value,
        bits_per_char=6,
        alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+-$",
    )


def _compress(uncompressed: str, *, bits_per_char: int, alphabet: str) -> str:
    if uncompressed == "":
        return ""

    dictionary: dict[str, int] = {}
    dictionary_to_create: dict[str, bool] = {}
    c = ""
    wc = ""
    w = ""
    enlarge_in = 2
    dict_size = 3
    num_bits = 2
    data: list[str] = []
    data_val = 0
    data_position = 0

    def write_bit(bit: int) -> None:
        nonlocal data_val, data_position
        data_val = (data_val << 1) | bit
        if data_position == bits_per_char - 1:
            data_position = 0
            data.append(alphabet[data_val])
            data_val = 0
        else:
            data_position += 1

    def write_value(value: int, bit_count: int) -> None:
        for _ in range(bit_count):
            write_bit(value & 1)
            value >>= 1

    for c in uncompressed:
        if c not in dictionary:
            dictionary[c] = dict_size
            dict_size += 1
            dictionary_to_create[c] = True

        wc = w + c
        if wc in dictionary:
            w = wc
            continue

        if w in dictionary_to_create:
            char_code = ord(w[0])
            if char_code < 256:
                write_value(0, num_bits)
                write_value(char_code, 8)
            else:
                write_value(1, num_bits)
                write_value(char_code, 16)
            enlarge_in -= 1
            if enlarge_in == 0:
                enlarge_in = 2**num_bits
                num_bits += 1
            del dictionary_to_create[w]
        else:
            write_value(dictionary[w], num_bits)

        enlarge_in -= 1
        if enlarge_in == 0:
            enlarge_in = 2**num_bits
            num_bits += 1

        dictionary[wc] = dict_size
        dict_size += 1
        w = c

    if w:
        if w in dictionary_to_create:
            char_code = ord(w[0])
            if char_code < 256:
                write_value(0, num_bits)
                write_value(char_code, 8)
            else:
                write_value(1, num_bits)
                write_value(char_code, 16)
            enlarge_in -= 1
            if enlarge_in == 0:
                enlarge_in = 2**num_bits
                num_bits += 1
            del dictionary_to_create[w]
        else:
            write_value(dictionary[w], num_bits)
        enlarge_in -= 1
        if enlarge_in == 0:
            num_bits += 1

    write_value(2, num_bits)

    while True:
        data_val <<= 1
        if data_position == bits_per_char - 1:
            data.append(alphabet[data_val])
            break
        data_position += 1

    return "".join(data)


__all__ = ["CenstatdJsonSelector"]
