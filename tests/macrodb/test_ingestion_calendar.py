"""Calendar semantics for provider-agnostic ingestion parsing."""

from __future__ import annotations

from datetime import date

import pytest

from macro_foundry.enums import Frequency
from macro_foundry.ingestion.runtime.calendar import period_bounds


@pytest.mark.no_db
def test_period_bounds_handles_second_half_semi_annual_anchor() -> None:
    assert period_bounds(date(2026, 10, 15), Frequency.SEMI_ANNUAL) == (
        date(2026, 7, 1),
        date(2026, 12, 31),
    )
