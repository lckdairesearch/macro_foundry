"""Selector contract coverage for the Japan e-Stat value-filter selector."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from macro_foundry.enums import Frequency
from macro_foundry.ingestion.runtime.selectors import get_selector


@pytest.mark.no_db
def test_estat_value_filter_selector_extracts_matching_dimension_values() -> None:
    selector = get_selector("estat_value_filter")

    result = selector.extract(
        {
            "GET_STATS_DATA": {
                "RESULT": {"STATUS": 0},
                "STATISTICAL_DATA": {
                    "DATA_INF": {
                        "VALUE": [
                            {
                                "@cat01": "headline",
                                "@area": "00000",
                                "@time": "2026000101",
                                "$": "101.2",
                            },
                            {
                                "@cat01": "core",
                                "@area": "00000",
                                "@time": "2026000101",
                                "$": "99.8",
                            },
                            {
                                "@cat01": "headline",
                                "@area": "00000",
                                "@time": "2026000201",
                                "$": "***",
                            },
                        ],
                    },
                },
            },
        },
        {
            "values_path": "GET_STATS_DATA.STATISTICAL_DATA.DATA_INF.VALUE",
            "value_dimension_filter": {"@cat01": "headline", "@area": "00000"},
            "time_field": "@time",
            "value_field": "$",
            "frequency": Frequency.MONTHLY.value,
            "missing_value_tokens": ["***"],
            "snapshot_vintage_date": "2026-06-10",
        },
    )

    assert result.outcome == "data"
    assert result.observations == [
        (
            date(2026, 1, 1),
            date(2026, 1, 31),
            Decimal("101.2"),
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
def test_estat_value_filter_selector_reports_result_status_errors() -> None:
    selector = get_selector("estat_value_filter")

    result = selector.extract(
        {"GET_STATS_DATA": {"RESULT": {"STATUS": 100, "ERROR_MSG": "Invalid appId"}}},
        {
            "values_path": "GET_STATS_DATA.STATISTICAL_DATA.DATA_INF.VALUE",
            "value_dimension_filter": {"@cat01": "headline"},
            "time_field": "@time",
            "value_field": "$",
            "frequency": Frequency.MONTHLY.value,
        },
    )

    assert result.outcome == "provider_error"
    assert result.observations == []
    assert result.error_message == "provider error 100: Invalid appId"


@pytest.mark.no_db
def test_estat_value_filter_selector_reports_success_with_no_matching_values() -> None:
    selector = get_selector("estat_value_filter")

    result = selector.extract(
        {
            "GET_STATS_DATA": {
                "RESULT": {"STATUS": 0},
                "STATISTICAL_DATA": {
                    "DATA_INF": {
                        "VALUE": {"@cat01": "core", "@time": "2026000101", "$": "99.8"},
                    },
                },
            },
        },
        {
            "values_path": "GET_STATS_DATA.STATISTICAL_DATA.DATA_INF.VALUE",
            "value_dimension_filter": {"@cat01": "headline"},
            "time_field": "@time",
            "value_field": "$",
            "frequency": Frequency.MONTHLY.value,
        },
    )

    assert result.outcome == "empty"
    assert result.observations == []
    assert result.error_message is None
