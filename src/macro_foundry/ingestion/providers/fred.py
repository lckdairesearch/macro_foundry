"""FRED client helpers and provider-specific period parsing."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any, Protocol

import httpx

from macro_foundry.enums import Frequency
from macro_foundry.ingestion.runtime.calendar import period_bounds


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

    async def fetch_series_metadata(
        self,
        series_id: str,
        *,
        endpoint_path: str = "/series",
    ) -> FredSeriesMetadata:
        """Fetch normalized metadata for one FRED series."""

    async def fetch_series_observations(
        self,
        series_id: str,
        *,
        observation_start: date | None = None,
        endpoint_path: str = "/series/observations",
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

    async def fetch_series_metadata(
        self,
        series_id: str,
        *,
        endpoint_path: str = "/series",
    ) -> FredSeriesMetadata:
        """Fetch normalized metadata from ``/series``."""

        payload = await self._get_json(endpoint_path, {"series_id": series_id})
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
        endpoint_path: str = "/series/observations",
    ) -> list[FredObservation]:
        """Fetch latest-snapshot observations from ``/series/observations``."""

        params: dict[str, Any] = {"series_id": series_id}
        if observation_start is not None:
            params["observation_start"] = observation_start.isoformat()

        payload = await self._get_json(endpoint_path, params)
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

    return period_bounds(period_anchor, frequency)


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
