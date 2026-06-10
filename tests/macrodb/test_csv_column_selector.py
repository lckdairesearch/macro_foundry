"""Selector contract coverage for the CSV-column selector."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from macro_foundry.enums import Frequency
from macro_foundry.ingestion.runtime.selectors import get_selector


@pytest.mark.no_db
def test_csv_column_selector_extracts_monthly_observations() -> None:
    selector = get_selector("csv_column")

    result = selector.extract(
        "period,value\n2026-01-01,318.2\n2026-02-01,.\n",
        {
            "period_column": "period",
            "value_column": "value",
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
def test_csv_column_selector_handles_delimiter_and_bom_header_edge_case() -> None:
    selector = get_selector("csv_column")

    result = selector.extract(
        "\ufeffDATE;OBS_VALUE\n2026-04-15;42.5\n",
        {
            "period_column": "DATE",
            "value_column": "OBS_VALUE",
            "frequency": Frequency.QUARTERLY.value,
            "delimiter": ";",
        },
    )

    assert result.outcome == "data"
    assert result.observations == [
        (
            date(2026, 4, 1),
            date(2026, 6, 30),
            Decimal("42.5"),
            None,
        ),
    ]


@pytest.mark.no_db
def test_csv_column_selector_reports_provider_error_csv_wrappers() -> None:
    selector = get_selector("csv_column")

    result = selector.extract(
        "error_code,error_message\n403,Forbidden API key\n",
        {
            "period_column": "period",
            "value_column": "value",
            "frequency": Frequency.MONTHLY.value,
        },
    )

    assert result.outcome == "provider_error"
    assert result.observations == []
    assert result.error_message == "provider error 403: Forbidden API key"


@pytest.mark.no_db
def test_csv_column_selector_reports_success_with_no_data() -> None:
    selector = get_selector("csv_column")

    result = selector.extract(
        "period,value\n",
        {
            "period_column": "period",
            "value_column": "value",
            "frequency": Frequency.MONTHLY.value,
        },
    )

    assert result.outcome == "empty"
    assert result.observations == []
    assert result.error_message is None
