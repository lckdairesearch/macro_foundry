"""OpenAI-backed LLMCallable provider for the onboarding agent."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

import openai
from pydantic import BaseModel

from macro_foundry.agent.llm_retry import TransientLLMError, call_with_retry
from macro_foundry.agent.roles import RoleConfig, resolve_model

T = TypeVar("T", bound=BaseModel)

_LLM_TIMEOUT_S = 60.0

# Per-1k-token pricing table: (prompt_usd_per_1k, completion_usd_per_1k)
_COST_TABLE: dict[str, tuple[float, float]] = {
    "gpt-4o": (0.005, 0.015),
    "gpt-4o-mini": (0.00015, 0.0006),
    "gpt-4-turbo": (0.010, 0.030),
    "gpt-4": (0.030, 0.060),
    "gpt-3.5-turbo": (0.0005, 0.0015),
    "o3": (0.010, 0.040),
    "o3-mini": (0.0011, 0.0044),
    "o1": (0.015, 0.060),
    "o1-mini": (0.003, 0.012),
}


class LLMTimeoutError(Exception):
    """Raised when an LLM call exceeds the 60-second operational timeout."""


def estimate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    """Return a USD cost estimate for one LLM call; returns 0.0 for unknown models."""
    rates = _COST_TABLE.get(model)
    if rates is None:
        return 0.0
    return (prompt_tokens * rates[0] + completion_tokens * rates[1]) / 1000.0


def _is_transient(exc: Exception) -> bool:
    if isinstance(exc, openai.RateLimitError):
        return True
    if isinstance(exc, openai.APIStatusError) and exc.status_code >= 500:
        return True
    if isinstance(exc, (openai.APITimeoutError, asyncio.TimeoutError)):
        return True
    return False


async def _parse_call(
    client: openai.AsyncOpenAI,
    *,
    model: str,
    messages: list[dict[str, str]],
    response_format: type[T],
    temperature: float | None,
    max_tokens: int,
    reasoning_effort: str | None,
) -> dict[str, Any]:
    """Make one openai.beta.chat.completions.parse call and return a usage+domain dict."""
    kwargs: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "response_format": response_format,
        "max_tokens": max_tokens,
    }
    if reasoning_effort is not None:
        kwargs["reasoning_effort"] = reasoning_effort
    else:
        kwargs["temperature"] = temperature

    t0 = time.monotonic()
    try:
        response = await asyncio.wait_for(
            client.beta.chat.completions.parse(**kwargs),
            timeout=_LLM_TIMEOUT_S,
        )
    except (openai.RateLimitError, openai.APIStatusError, openai.APITimeoutError) as exc:
        if _is_transient(exc):
            raise TransientLLMError(str(exc)) from exc
        raise
    except asyncio.TimeoutError as exc:
        raise TransientLLMError(f"LLM call timed out after {_LLM_TIMEOUT_S}s") from exc

    latency_ms = int((time.monotonic() - t0) * 1000)
    usage = response.usage
    parsed = response.choices[0].message.parsed
    return {
        **parsed.model_dump(),
        "prompt_tokens": usage.prompt_tokens,
        "completion_tokens": usage.completion_tokens,
        "total_tokens": usage.total_tokens,
        "cost_estimate_usd": estimate_cost(model, usage.prompt_tokens, usage.completion_tokens),
        "latency_ms": latency_ms,
    }


def make_openai_llm_callable(
    role_config: RoleConfig,
    response_type: type[T],
    *,
    client: openai.AsyncOpenAI,
) -> Callable[[list[dict[str, str]]], Awaitable[dict[str, Any]]]:
    """Return an LLMCallable backed by OpenAI structured outputs for the given role."""

    async def _call(messages: list[dict[str, str]]) -> dict[str, Any]:
        model = resolve_model(role_config)
        decode = role_config.decode

        async def _attempt() -> dict[str, Any]:
            return await _parse_call(
                client,
                model=model,
                messages=messages,
                response_format=response_type,
                temperature=decode.temperature,
                max_tokens=decode.max_tokens,
                reasoning_effort=decode.reasoning_effort,
            )

        return await call_with_retry(_attempt)

    return _call


def make_openai_reviewer_callable(
    role_config: RoleConfig,
    response_type: type[T],
    *,
    client: openai.AsyncOpenAI,
) -> Callable[..., Awaitable[dict[str, Any]]]:
    """Return a ReviewerLLMCallable backed by OpenAI; honours task_hint model tiering."""

    async def _call(
        messages: list[dict[str, str]],
        *,
        task_hint: str | None = None,
    ) -> dict[str, Any]:
        model = resolve_model(role_config, task_hint=task_hint)
        decode = role_config.decode

        async def _attempt() -> dict[str, Any]:
            return await _parse_call(
                client,
                model=model,
                messages=messages,
                response_format=response_type,
                temperature=decode.temperature,
                max_tokens=decode.max_tokens,
                reasoning_effort=decode.reasoning_effort,
            )

        return await call_with_retry(_attempt)

    return _call


def openai_client_from_env() -> openai.AsyncOpenAI:
    """Build an AsyncOpenAI client from OPENAI_API_KEY in the environment."""
    return openai.AsyncOpenAI()


__all__ = [
    "LLMTimeoutError",
    "estimate_cost",
    "make_openai_llm_callable",
    "make_openai_reviewer_callable",
    "openai_client_from_env",
]
