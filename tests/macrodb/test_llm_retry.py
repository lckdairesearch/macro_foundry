"""Tests for the LLM call retry wrapper."""

from __future__ import annotations

import pytest

from macro_foundry.agent.llm_retry import TransientLLMError, call_with_retry


@pytest.mark.no_db
@pytest.mark.asyncio
async def test_call_with_retry_succeeds_on_first_attempt() -> None:
    calls = 0

    async def succeed() -> str:
        nonlocal calls
        calls += 1
        return "ok"

    result = await call_with_retry(succeed)
    assert result == "ok"
    assert calls == 1


@pytest.mark.no_db
@pytest.mark.asyncio
async def test_call_with_retry_retries_on_transient_error_then_succeeds() -> None:
    calls = 0

    async def fail_twice_then_succeed() -> str:
        nonlocal calls
        calls += 1
        if calls < 3:
            raise TransientLLMError("rate limited")
        return "recovered"

    result = await call_with_retry(fail_twice_then_succeed, base_delay=0.0)
    assert result == "recovered"
    assert calls == 3


@pytest.mark.no_db
@pytest.mark.asyncio
async def test_call_with_retry_raises_after_max_retries_exhausted() -> None:
    calls = 0

    async def always_fail() -> str:
        nonlocal calls
        calls += 1
        raise TransientLLMError("always fails")

    with pytest.raises(TransientLLMError, match="always fails"):
        await call_with_retry(always_fail, max_retries=3, base_delay=0.0)

    assert calls == 4  # 1 initial + 3 retries


@pytest.mark.no_db
@pytest.mark.asyncio
async def test_call_with_retry_does_not_retry_non_transient_errors() -> None:
    calls = 0

    async def raise_value_error() -> str:
        nonlocal calls
        calls += 1
        raise ValueError("non-transient")

    with pytest.raises(ValueError, match="non-transient"):
        await call_with_retry(raise_value_error, base_delay=0.0)

    assert calls == 1
