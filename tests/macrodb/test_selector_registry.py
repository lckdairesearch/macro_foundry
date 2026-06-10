"""Selector-registry coverage."""

from __future__ import annotations

import pytest

from macro_foundry.ingestion.runtime.selectors import list_selector_types


@pytest.mark.no_db
def test_second_wave_selectors_are_registered() -> None:
    assert list_selector_types() == [
        "censtatd_json",
        "csv_column",
        "estat_value_filter",
        "json_path",
    ]
