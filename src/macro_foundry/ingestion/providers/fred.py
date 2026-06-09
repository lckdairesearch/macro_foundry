"""FRED client helpers and provider-specific period parsing."""

from __future__ import annotations

from calendar import monthrange
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, Protocol

import httpx

from macro_foundry.enums import Frequency


@dataclass(frozen=True, slots=True)
class FredSeriesMetadata:
    """Normalized FRED series metadata used by the bootstrap flow."""

    series_id: str
    title: str
    frequency: Frequency
    observation_start: date | None
    observation_end: date | None


@dataclass(frozen=True, slots=True)
class FredObservation:
    """One latest-snapshot observation returned by FRED."""

    period_anchor: date
    value: Decimal | None


class FredClientProtocol(Protocol):
    """Protocol for the FRED client used in orchestration and tests."""

    async def fetch_series_metadata(self, series_id: str) -> FredSeriesMetadata:
        """Fetch normalized metadata for one FRED series."""

    async def fetch_series_observations(
        self,
        series_id: str,
        *,
        observation_start: date | None = None,
    ) -> list[FredObservation]:
        """Fetch latest-snapshot observations for one FRED series."""


class FredClient:
    """Small async client for the FRED JSON API."""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = "https://api.stlouisfed.org/fred",
        timeout: float = 30.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._api_key = api_key
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(base_url=base_url, timeout=timeout)

    async def __aenter__(self) -> "FredClient":
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        """Close the underlying HTTP client when owned by this instance."""

        if self._owns_client:
            await self._client.aclose()

    async def fetch_series_metadata(self, series_id: str) -> FredSeriesMetadata:
        """Fetch normalized metadata from ``/series``."""

        payload = await self._get_json("/series", {"series_id": series_id})
        series_rows = payload.get("seriess", [])
        if len(series_rows) != 1:
            raise ValueError(f"FRED returned {len(series_rows)} metadata rows for {series_id!r}")

        row = series_rows[0]
        return FredSeriesMetadata(
            series_id=series_id,
            title=str(row["title"]),
            frequency=_parse_frequency(row),
            observation_start=_parse_optional_date(row.get("observation_start")),
            observation_end=_parse_optional_date(row.get("observation_end")),
        )

    async def fetch_series_observations(
        self,
        series_id: str,
        *,
        observation_start: date | None = None,
    ) -> list[FredObservation]:
        """Fetch latest-snapshot observations from ``/series/observations``."""

        params: dict[str, Any] = {"series_id": series_id}
        if observation_start is not None:
            params["observation_start"] = observation_start.isoformat()

        payload = await self._get_json("/series/observations", params)
        return [
            FredObservation(
                period_anchor=date.fromisoformat(str(row["date"])),
                value=_parse_optional_decimal(row.get("value")),
            )
            for row in payload.get("observations", [])
        ]

    async def _get_json(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        response = await self._client.get(
            path,
            params={
                "api_key": self._api_key,
                "file_type": "json",
                **params,
            },
        )
        response.raise_for_status()
        payload = response.json()
        if "error_code" in payload:
            raise ValueError(
                f"FRED API error {payload['error_code']}: {payload.get('error_message', 'unknown error')}",
            )
        return payload


def fred_period_bounds(
    period_anchor: date,
    *,
    frequency: Frequency,
) -> tuple[date, date]:
    """Map a FRED period anchor to macrodb period bounds."""

    if frequency is Frequency.DAILY:
        return period_anchor, period_anchor
    if frequency is Frequency.WEEKLY:
        return period_anchor, period_anchor + timedelta(days=6)
    if frequency is Frequency.MONTHLY:
        period_start = period_anchor.replace(day=1)
        return period_start, date(
            period_start.year,
            period_start.month,
            monthrange(period_start.year, period_start.month)[1],
        )
    if frequency is Frequency.QUARTERLY:
        quarter_start_month = ((period_anchor.month - 1) // 3) * 3 + 1
        period_start = date(period_anchor.year, quarter_start_month, 1)
        period_end_month = quarter_start_month + 2
        return period_start, date(
            period_start.year,
            period_end_month,
            monthrange(period_start.year, period_end_month)[1],
        )
    if frequency is Frequency.SEMI_ANNUAL:
        period_start_month = 1 if period_anchor.month <= 6 else 7
        period_start = date(period_anchor.year, period_start_month, 1)
        period_end_month = 6 if period_start_month == 1 else 12
        return period_start, date(
            period_start.year,
            period_end_month,
            monthrange(period_start.year, period_end_month)[1],
        )
    if frequency is Frequency.ANNUAL:
        period_start = date(period_anchor.year, 1, 1)
        return period_start, date(period_anchor.year, 12, 31)
    raise ValueError(f"Unsupported FRED frequency {frequency.value!r}")


def _parse_frequency(row: dict[str, Any]) -> Frequency:
    frequency_token = str(row.get("frequency_short") or row.get("frequency") or "").upper()
    mapping = {
        "D": Frequency.DAILY,
        "DAILY": Frequency.DAILY,
        "W": Frequency.WEEKLY,
        "WEEKLY": Frequency.WEEKLY,
        "M": Frequency.MONTHLY,
        "MONTHLY": Frequency.MONTHLY,
        "Q": Frequency.QUARTERLY,
        "QUARTERLY": Frequency.QUARTERLY,
        "SA": Frequency.SEMI_ANNUAL,
        "SEMIANNUAL": Frequency.SEMI_ANNUAL,
        "SEMI-ANNUAL": Frequency.SEMI_ANNUAL,
        "A": Frequency.ANNUAL,
        "ANNUAL": Frequency.ANNUAL,
    }
    try:
        return mapping[frequency_token]
    except KeyError as exc:
        raise ValueError(f"Unsupported FRED frequency token {frequency_token!r}") from exc


def _parse_optional_date(raw_value: Any) -> date | None:
    if raw_value in (None, "", "."):
        return None
    return date.fromisoformat(str(raw_value))


def _parse_optional_decimal(raw_value: Any) -> Decimal | None:
    if raw_value in (None, "", "."):
        return None
    try:
        return Decimal(str(raw_value))
    except InvalidOperation as exc:
        raise ValueError(f"Invalid FRED numeric value {raw_value!r}") from exc


__all__ = [
    "FredClient",
    "FredClientProtocol",
    "FredObservation",
    "FredSeriesMetadata",
    "fred_period_bounds",
]
