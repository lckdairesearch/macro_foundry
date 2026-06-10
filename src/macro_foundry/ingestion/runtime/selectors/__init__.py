"""Selector registry for the generic ingestion runtime."""

from __future__ import annotations

from macro_foundry.ingestion.runtime.types import Selector

from .json_path import JsonPathSelector

_SELECTORS: dict[str, Selector] = {
    JsonPathSelector.name: JsonPathSelector(),
}


def get_selector(selector_type: str) -> Selector:
    """Return a registered selector by database selector_type."""

    try:
        return _SELECTORS[selector_type]
    except KeyError as exc:
        raise ValueError(f"Unknown selector_type {selector_type!r}") from exc


def list_selector_types() -> list[str]:
    """Return registered selector_type values."""

    return sorted(_SELECTORS)


__all__ = ["get_selector", "list_selector_types"]
