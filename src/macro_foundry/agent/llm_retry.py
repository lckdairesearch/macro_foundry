"""Retry wrapper for transient LLM call failures."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar

T = TypeVar("T")


class TransientLLMError(Exception):
    """Raised by LLM call sites when the failure is retryable (rate limit, timeout, 5xx)."""


async def call_with_retry(
    coro_factory: Callable[[], Awaitable[T]],
    *,
    max_retries: int = 3,
    base_delay: float = 1.0,
) -> T:
    """Call ``coro_factory()`` and retry up to ``max_retries`` times on TransientLLMError.

    Backoff is ``base_delay * 2**attempt`` seconds between retries.
    Non-transient exceptions propagate immediately without retry.
    Raises the final TransientLLMError when all retries are exhausted.
    """
    last_exc: TransientLLMError | None = None
    for attempt in range(max_retries + 1):
        try:
            return await coro_factory()
        except TransientLLMError as exc:
            last_exc = exc
            if attempt < max_retries:
                await asyncio.sleep(base_delay * (2**attempt))
    raise last_exc  # type: ignore[misc]


__all__ = ["TransientLLMError", "call_with_retry"]
