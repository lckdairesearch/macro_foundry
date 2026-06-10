"""Tests for the probe fetch timeout wrapper."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from macro_foundry.agent.probe import ProbeTimeoutError, fetch_probe


@pytest.mark.no_db
@pytest.mark.asyncio
async def test_fetch_probe_returns_body_on_success(monkeypatch: pytest.MonkeyPatch) -> None:
    response = MagicMock()
    response.text = "hello"
    mock_get = AsyncMock(return_value=response)

    monkeypatch.setattr("httpx.AsyncClient.get", mock_get)

    result = await fetch_probe("https://example.com/data")
    assert result == "hello"
    mock_get.assert_awaited_once()


@pytest.mark.no_db
@pytest.mark.asyncio
async def test_fetch_probe_raises_on_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    async def slow_get(*args: object, **kwargs: object) -> object:
        await asyncio.sleep(999)

    monkeypatch.setattr("httpx.AsyncClient.get", slow_get)

    with pytest.raises(ProbeTimeoutError, match="timed out"):
        await fetch_probe("https://example.com/slow", timeout=0.001)
