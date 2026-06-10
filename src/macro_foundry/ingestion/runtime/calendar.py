"""Provider-agnostic period-bound utilities for ingestion selectors."""

from __future__ import annotations

from calendar import monthrange
from datetime import date, timedelta

from macro_foundry.enums import Frequency


def period_bounds(anchor: date, frequency: Frequency) -> tuple[date, date]:
    """Return macrodb period bounds for an observation anchor date."""

    if frequency is Frequency.DAILY:
        return anchor, anchor
    if frequency is Frequency.WEEKLY:
        return anchor, anchor + timedelta(days=6)
    if frequency is Frequency.MONTHLY:
        period_start = anchor.replace(day=1)
        return period_start, date(
            period_start.year,
            period_start.month,
            monthrange(period_start.year, period_start.month)[1],
        )
    if frequency is Frequency.QUARTERLY:
        quarter_start_month = ((anchor.month - 1) // 3) * 3 + 1
        period_start = date(anchor.year, quarter_start_month, 1)
        period_end_month = quarter_start_month + 2
        return period_start, date(
            period_start.year,
            period_end_month,
            monthrange(period_start.year, period_end_month)[1],
        )
    if frequency is Frequency.SEMI_ANNUAL:
        period_start_month = 1 if anchor.month <= 6 else 7
        period_start = date(anchor.year, period_start_month, 1)
        period_end_month = 6 if period_start_month == 1 else 12
        return period_start, date(
            period_start.year,
            period_end_month,
            monthrange(period_start.year, period_end_month)[1],
        )
    if frequency is Frequency.ANNUAL:
        period_start = date(anchor.year, 1, 1)
        return period_start, date(anchor.year, 12, 31)
    raise ValueError(f"Unsupported frequency {frequency.value!r}")


__all__ = ["period_bounds"]
