"""Selector contract coverage for the generic JSON-path selector."""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from macro_foundry.enums import Frequency
from macro_foundry.ingestion.runtime.selectors import get_selector

_FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures"


@pytest.mark.no_db
def test_json_path_selector_extracts_fred_shaped_observations() -> None:
    selector = get_selector("json_path")
    payload = json.loads((_FIXTURES_DIR / "json_path_fred_observations.json").read_text())

    result = selector.extract(
        payload,
        {
            "records_path": "observations",
            "period_anchor_field": "date",
            "value_field": "value",
            "frequency": Frequency.MONTHLY.value,
            "missing_value_tokens": ["."],
            "snapshot_vintage_date": "2026-06-10",
        },
    )

    assert result.outcome == "data"
    assert result.observations == [
        (
            date(2026, 1, 1),
            date(2026, 1, 31),
            Decimal("318.2"),
            date(2026, 6, 10),
        ),
        (
            date(2026, 2, 1),
            date(2026, 2, 28),
            None,
            date(2026, 6, 10),
        ),
    ]


@pytest.mark.no_db
def test_json_path_selector_reports_provider_error_wrappers() -> None:
    selector = get_selector("json_path")

    result = selector.extract(
        {"Information": "demo API key rate limit reached"},
        {
            "records_path": "observations",
            "period_anchor_field": "date",
            "value_field": "value",
            "frequency": Frequency.MONTHLY.value,
        },
    )

    assert result.outcome == "provider_error"
    assert result.observations == []
    assert result.error_message == "demo API key rate limit reached"


@pytest.mark.no_db
def test_json_path_selector_reports_success_with_no_data() -> None:
    selector = get_selector("json_path")

    result = selector.extract(
        {"observations": []},
        {
            "records_path": "observations",
            "period_anchor_field": "date",
            "value_field": "value",
            "frequency": Frequency.MONTHLY.value,
        },
    )

    assert result.outcome == "empty"
    assert result.observations == []
    assert result.error_message is None
