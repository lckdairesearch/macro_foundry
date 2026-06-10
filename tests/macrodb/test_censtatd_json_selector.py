"""Selector contract coverage for the Hong Kong CenStatD JSON selector."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from macro_foundry.enums import Frequency
from macro_foundry.ingestion.runtime.selectors import get_selector


@pytest.mark.no_db
def test_censtatd_json_selector_extracts_leaf_code_observations() -> None:
    selector = get_selector("censtatd_json")

    result = selector.extract(
        {
            "data": [
                {"period": "2026-01", "value": "100", "code": "0101"},
                {"period": "2026-01", "value": "12.4", "code": "010101"},
                {"period": "2026-02", "value": "-", "code": "010101"},
            ],
        },
        {
            "records_path": "data",
            "period_field": "period",
            "value_field": "value",
            "frequency": Frequency.MONTHLY.value,
            "hierarchy_code_field": "code",
            "hierarchy_code_length": 6,
            "missing_value_tokens": ["-"],
            "snapshot_vintage_date": "2026-06-10",
        },
    )

    assert result.outcome == "data"
    assert result.observations == [
        (
            date(2026, 1, 1),
            date(2026, 1, 31),
            Decimal("12.4"),
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
def test_censtatd_json_selector_reports_provider_error_wrappers() -> None:
    selector = get_selector("censtatd_json")

    result = selector.extract(
        {"errorCode": "E001", "errorMessage": "Invalid compressed query parameter"},
        {
            "records_path": "data",
            "period_field": "period",
            "value_field": "value",
            "frequency": Frequency.MONTHLY.value,
            "hierarchy_code_field": "code",
            "hierarchy_code_length": 6,
        },
    )

    assert result.outcome == "provider_error"
    assert result.observations == []
    assert (
        result.error_message
        == "provider error E001: Invalid compressed query parameter"
    )


@pytest.mark.no_db
def test_censtatd_json_selector_reports_success_with_no_data() -> None:
    selector = get_selector("censtatd_json")

    result = selector.extract(
        {"data": [{"period": "2026-01", "value": "100", "code": "0101"}]},
        {
            "records_path": "data",
            "period_field": "period",
            "value_field": "value",
            "frequency": Frequency.MONTHLY.value,
            "hierarchy_code_field": "code",
            "hierarchy_code_length": 6,
        },
    )

    assert result.outcome == "empty"
    assert result.observations == []
    assert result.error_message is None


@pytest.mark.no_db
def test_censtatd_json_selector_prepares_lz_string_encoded_request_params() -> None:
    selector = get_selector("censtatd_json")

    params = selector.prepare_request_params(
        {
            "static_params": {"lang": "en"},
            "compressed_param_name": "query",
            "compressed_params": {
                "dataset": "cpi",
                "lang": "en",
            },
        },
    )

    assert params["lang"] == "en"
    assert params["query"] != '{"dataset":"cpi","lang":"en"}'
    assert set(params["query"]) <= set(
        "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+-$"
    )
