"""Probe fetch helper with a 30-second timeout."""

from __future__ import annotations

import asyncio

import httpx


class ProbeTimeoutError(Exception):
    """Raised when a probe fetch exceeds its timeout budget."""


async def fetch_probe(url: str, *, timeout: float = 30.0) -> str:
    """Fetch ``url`` and return the response body text.

    Raises ProbeTimeoutError if the request does not complete within ``timeout`` seconds.
    """
    try:
        async with httpx.AsyncClient() as client:
            response = await asyncio.wait_for(client.get(url), timeout=timeout)
        return response.text
    except asyncio.TimeoutError:
        raise ProbeTimeoutError(f"{url} timed out after {timeout}s")


__all__ = ["ProbeTimeoutError", "fetch_probe"]
