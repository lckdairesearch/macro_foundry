"""Tests for the OpenAI LLMCallable provider (issue 57)."""

from __future__ import annotations

import asyncio
import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from macro_foundry.agent.llm_openai import (
    estimate_cost,
    make_openai_llm_callable,
    make_openai_reviewer_callable,
)
from macro_foundry.agent.llm_retry import TransientLLMError
from macro_foundry.agent.llm_schemas import DraftOutput, ResearchOutput, ReviewerOutput
from macro_foundry.agent.roles import (
    AgentRole,
    DecodeParams,
    LLMProvider,
    RoleConfig,
    default_role_configs,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _research_role() -> RoleConfig:
    return RoleConfig(
        role=AgentRole.RESEARCHER,
        default_model="gpt-4o",
        provider=LLMProvider.OPENAI,
        decode=DecodeParams(temperature=0.2, max_tokens=2000),
    )


def _governance_role() -> RoleConfig:
    return RoleConfig(
        role=AgentRole.GOVERNANCE_REVIEWER,
        default_model="gpt-4o",
        provider=LLMProvider.OPENAI,
        models_by_task={"selector_code_review": "gpt-4o-mini"},
        decode=DecodeParams(temperature=0.0, max_tokens=1000),
    )


def _mock_parse_response(parsed_obj: Any, prompt_tokens: int = 50, completion_tokens: int = 30) -> MagicMock:
    """Build a mock that looks like openai ParsedChatCompletion."""
    usage = MagicMock()
    usage.prompt_tokens = prompt_tokens
    usage.completion_tokens = completion_tokens
    usage.total_tokens = prompt_tokens + completion_tokens

    message = MagicMock()
    message.parsed = parsed_obj

    choice = MagicMock()
    choice.message = message

    response = MagicMock()
    response.usage = usage
    response.choices = [choice]
    return response


# ---------------------------------------------------------------------------
# Tracer bullet: make_openai_llm_callable returns usage fields from a mock client
# ---------------------------------------------------------------------------

@pytest.mark.no_db
@pytest.mark.asyncio
async def test_make_openai_llm_callable_returns_usage_and_domain_fields() -> None:
    parsed = ResearchOutput(
        source_summary="FRED publishes CPI via JSON API.",
        existing_catalog_hits=[],
        ambiguity_flags=[],
        credential_gap_proposals=[],
    )
    mock_client = MagicMock()
    mock_client.beta.chat.completions.parse = AsyncMock(
        return_value=_mock_parse_response(parsed, prompt_tokens=40, completion_tokens=20)
    )

    callable_ = make_openai_llm_callable(_research_role(), ResearchOutput, client=mock_client)
    result = await callable_([{"role": "user", "content": "Onboard FRED CPI"}])

    assert result["source_summary"] == "FRED publishes CPI via JSON API."
    assert result["existing_catalog_hits"] == []
    assert result["ambiguity_flags"] == []
    assert result["prompt_tokens"] == 40
    assert result["completion_tokens"] == 20
    assert result["total_tokens"] == 60
    assert isinstance(result["cost_estimate_usd"], float)
    assert isinstance(result["latency_ms"], int)


@pytest.mark.no_db
@pytest.mark.asyncio
async def test_make_openai_llm_callable_passes_decode_params_to_api() -> None:
    parsed = ResearchOutput(
        source_summary="Summary.",
        existing_catalog_hits=[],
        ambiguity_flags=[],
        credential_gap_proposals=[],
    )
    mock_client = MagicMock()
    mock_client.beta.chat.completions.parse = AsyncMock(
        return_value=_mock_parse_response(parsed)
    )
    role = _research_role()

    callable_ = make_openai_llm_callable(role, ResearchOutput, client=mock_client)
    await callable_([{"role": "user", "content": "test"}])

    call_kwargs = mock_client.beta.chat.completions.parse.call_args.kwargs
    assert call_kwargs["model"] == "gpt-4o"
    assert call_kwargs["temperature"] == 0.2
    assert call_kwargs["max_tokens"] == 2000
    assert call_kwargs["response_format"] is ResearchOutput


@pytest.mark.no_db
@pytest.mark.asyncio
async def test_gpt5_model_uses_max_completion_tokens() -> None:
    parsed = ResearchOutput(
        source_summary="Summary.",
        existing_catalog_hits=[],
        ambiguity_flags=[],
        credential_gap_proposals=[],
    )
    mock_client = MagicMock()
    mock_client.beta.chat.completions.parse = AsyncMock(
        return_value=_mock_parse_response(parsed)
    )
    role = RoleConfig(
        role=AgentRole.RESEARCHER,
        default_model="gpt-5.4",
        provider=LLMProvider.OPENAI,
        decode=DecodeParams(reasoning_effort="medium", max_tokens=2000),
    )

    callable_ = make_openai_llm_callable(role, ResearchOutput, client=mock_client)
    await callable_([{"role": "user", "content": "test"}])

    call_kwargs = mock_client.beta.chat.completions.parse.call_args.kwargs
    assert call_kwargs["model"] == "gpt-5.4"
    assert call_kwargs["max_completion_tokens"] == 2000
    assert "max_tokens" not in call_kwargs
    assert call_kwargs["reasoning_effort"] == "medium"
    assert "temperature" not in call_kwargs


# ---------------------------------------------------------------------------
# task_hint tiering: reviewer callable routes to models_by_task model
# ---------------------------------------------------------------------------

@pytest.mark.no_db
@pytest.mark.asyncio
async def test_reviewer_callable_uses_default_model_without_task_hint() -> None:
    parsed = ReviewerOutput(findings=[], bounce_to_drafter=False)
    mock_client = MagicMock()
    mock_client.beta.chat.completions.parse = AsyncMock(
        return_value=_mock_parse_response(parsed)
    )

    callable_ = make_openai_reviewer_callable(_governance_role(), ReviewerOutput, client=mock_client)
    await callable_([{"role": "user", "content": "review this"}])

    call_kwargs = mock_client.beta.chat.completions.parse.call_args.kwargs
    assert call_kwargs["model"] == "gpt-4o"


@pytest.mark.no_db
@pytest.mark.asyncio
async def test_reviewer_callable_routes_to_tiered_model_on_task_hint() -> None:
    parsed = ReviewerOutput(findings=[], bounce_to_drafter=False)
    mock_client = MagicMock()
    mock_client.beta.chat.completions.parse = AsyncMock(
        return_value=_mock_parse_response(parsed)
    )

    callable_ = make_openai_reviewer_callable(_governance_role(), ReviewerOutput, client=mock_client)
    await callable_(
        [{"role": "user", "content": "review this"}],
        task_hint="selector_code_review",
    )

    call_kwargs = mock_client.beta.chat.completions.parse.call_args.kwargs
    assert call_kwargs["model"] == "gpt-4o-mini"


# ---------------------------------------------------------------------------
# reasoning_effort is forwarded when set in DecodeParams
# ---------------------------------------------------------------------------

@pytest.mark.no_db
@pytest.mark.asyncio
async def test_reasoning_effort_forwarded_when_set() -> None:
    parsed = ReviewerOutput(findings=[], bounce_to_drafter=False)
    mock_client = MagicMock()
    mock_client.beta.chat.completions.parse = AsyncMock(
        return_value=_mock_parse_response(parsed)
    )
    role = RoleConfig(
        role=AgentRole.GOVERNANCE_REVIEWER,
        default_model="gpt-4o",
        provider=LLMProvider.OPENAI,
        decode=DecodeParams(reasoning_effort="medium", max_tokens=2000),
    )

    callable_ = make_openai_reviewer_callable(role, ReviewerOutput, client=mock_client)
    await callable_([{"role": "user", "content": "review"}])

    call_kwargs = mock_client.beta.chat.completions.parse.call_args.kwargs
    assert call_kwargs["reasoning_effort"] == "medium"


# ---------------------------------------------------------------------------
# Transient error wrapping and retry
# ---------------------------------------------------------------------------

@pytest.mark.no_db
@pytest.mark.asyncio
async def test_rate_limit_error_wraps_as_transient_and_retries() -> None:
    import openai as openai_lib

    parsed = ResearchOutput(
        source_summary="ok",
        existing_catalog_hits=[],
        ambiguity_flags=[],
        credential_gap_proposals=[],
    )
    call_count = 0

    async def _flaky(*_a: Any, **_kw: Any) -> Any:
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise openai_lib.RateLimitError(
                "rate limited",
                response=MagicMock(status_code=429),
                body=None,
            )
        return _mock_parse_response(parsed)

    mock_client = MagicMock()
    mock_client.beta.chat.completions.parse = _flaky

    callable_ = make_openai_llm_callable(_research_role(), ResearchOutput, client=mock_client)
    result = await callable_([{"role": "user", "content": "test"}])

    assert call_count == 3
    assert result["source_summary"] == "ok"


@pytest.mark.no_db
@pytest.mark.asyncio
async def test_rate_limit_exhaustion_propagates_transient_error() -> None:
    import openai as openai_lib

    async def _always_fail(*_a: Any, **_kw: Any) -> Any:
        raise openai_lib.RateLimitError(
            "always limited",
            response=MagicMock(status_code=429),
            body=None,
        )

    mock_client = MagicMock()
    mock_client.beta.chat.completions.parse = _always_fail

    callable_ = make_openai_llm_callable(_research_role(), ResearchOutput, client=mock_client)
    with pytest.raises(TransientLLMError):
        await callable_([{"role": "user", "content": "test"}])


@pytest.mark.no_db
@pytest.mark.asyncio
async def test_server_error_5xx_is_transient() -> None:
    import openai as openai_lib

    call_count = 0
    parsed = ResearchOutput(
        source_summary="recovered",
        existing_catalog_hits=[],
        ambiguity_flags=[],
        credential_gap_proposals=[],
    )

    async def _fail_then_succeed(*_a: Any, **_kw: Any) -> Any:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise openai_lib.InternalServerError(
                "server error",
                response=MagicMock(status_code=500),
                body=None,
            )
        return _mock_parse_response(parsed)

    mock_client = MagicMock()
    mock_client.beta.chat.completions.parse = _fail_then_succeed

    callable_ = make_openai_llm_callable(_research_role(), ResearchOutput, client=mock_client)
    result = await callable_([{"role": "user", "content": "test"}])
    assert result["source_summary"] == "recovered"
    assert call_count == 2


# ---------------------------------------------------------------------------
# Timeout handling
# ---------------------------------------------------------------------------

@pytest.mark.no_db
@pytest.mark.asyncio
async def test_timeout_wraps_as_transient_llm_error() -> None:
    async def _hang(*_a: Any, **_kw: Any) -> Any:
        raise asyncio.TimeoutError()

    mock_client = MagicMock()
    mock_client.beta.chat.completions.parse = _hang

    callable_ = make_openai_llm_callable(_research_role(), ResearchOutput, client=mock_client)
    with pytest.raises(TransientLLMError):
        await callable_([{"role": "user", "content": "test"}])


# ---------------------------------------------------------------------------
# Cost estimation
# ---------------------------------------------------------------------------

@pytest.mark.no_db
def test_estimate_cost_known_model() -> None:
    cost = estimate_cost("gpt-4o", prompt_tokens=1000, completion_tokens=500)
    assert cost > 0.0


@pytest.mark.no_db
def test_estimate_cost_unknown_model_returns_zero() -> None:
    cost = estimate_cost("gpt-5.4", prompt_tokens=1000, completion_tokens=500)
    assert cost == 0.0


@pytest.mark.no_db
def test_estimate_cost_zero_tokens_is_zero() -> None:
    assert estimate_cost("gpt-4o", prompt_tokens=0, completion_tokens=0) == 0.0


# ---------------------------------------------------------------------------
# LLM schemas: ResearchOutput, DraftOutput, ReviewerOutput
# ---------------------------------------------------------------------------

@pytest.mark.no_db
def test_research_output_schema_constructs() -> None:
    output = ResearchOutput(
        source_summary="FRED provides CPI.",
        existing_catalog_hits=[{"code": "US_CPI"}],
        ambiguity_flags=["unclear_frequency"],
        credential_gap_proposals=[],
    )
    assert output.source_summary == "FRED provides CPI."
    assert len(output.existing_catalog_hits) == 1


@pytest.mark.no_db
def test_draft_output_schema_defaults_to_empty() -> None:
    output = DraftOutput()
    assert output.proposal is None
    assert output.enum_gap_proposals == []
    assert output.harmonisation_items == []
    assert output.suggest_human_apply == []


@pytest.mark.no_db
def test_reviewer_output_schema_defaults_to_no_findings() -> None:
    output = ReviewerOutput()
    assert output.findings == []
    assert output.bounce_to_drafter is False


# ---------------------------------------------------------------------------
# Fixture-backed integration: openai callable through onboarding graph
# ---------------------------------------------------------------------------

@pytest.mark.no_db
@pytest.mark.asyncio
async def test_openai_callable_exercised_through_onboarding_graph() -> None:
    """
    Drives the onboarding graph's research node with an OpenAI callable backed
    by a fixture response.  No real network call is made — the httpx transport
    is replaced with a canned JSON fixture.
    """
    import openai as openai_lib
    from langgraph.checkpoint.memory import MemorySaver

    from macro_foundry.agent.graph import build_onboarding_graph
    from macro_foundry.agent.llm_schemas import DraftOutput, ResearchOutput, ReviewerOutput
    from macro_foundry.agent.skills import SkillRegistry

    # --- Fixture HTTP response for the OpenAI API (/v1/chat/completions) ---
    research_content = json.dumps({
        "source_summary": "FRED publishes CPI as JSON observations.",
        "existing_catalog_hits": [],
        "ambiguity_flags": [],
        "credential_gap_proposals": [],
    })
    draft_content = json.dumps({
        "proposal": {
            "concept": {"action": "new", "code": "CPI57", "name": "CPI57"},
            "family": {
                "action": "new",
                "code": "FAM_CPI57",
                "name": "CPI57 Family",
                "concept_code": "CPI57",
                "geography_code": "USA",
            },
            "series": {
                "action": "new",
                "code": "CPI57_SA_M",
                "name": "CPI57 SA Monthly",
                "frequency": "monthly",
                "measure": "level",
                "unit_kind": "index",
                "temporal_stock_flow": "index",
                "unit_scale": "one",
                "seasonal_adjustment": "NSA",
            },
            "source": {"provider_name": "USA FRED", "external_code": "CPIAUCSL"},
            "feed": {
                "selector_type": "json_path",
                "cron_schedule": "0 14 * * 5",
                "feed_method": "api",
            },
            "family_member": {"variant": "SA"},
        },
        "enum_gap_proposals": [],
        "harmonisation_items": [],
        "suggest_human_apply": [],
    })
    reviewer_content = json.dumps({
        "findings": [],
        "bounce_to_drafter": False,
    })

    def _openai_response(content: str) -> bytes:
        return json.dumps({
            "id": "chatcmpl-test",
            "object": "chat.completion",
            "created": 1717171717,
            "model": "gpt-4o",
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": content,
                        "tool_calls": None,
                        "refusal": None,
                    },
                    "logprobs": None,
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": 50,
                "completion_tokens": 30,
                "total_tokens": 80,
            },
            "system_fingerprint": "fp_test",
        }).encode()

    responses_queue = [
        _openai_response(research_content),
        _openai_response(draft_content),
        _openai_response(reviewer_content),
        _openai_response(reviewer_content),
    ]

    class _FixtureTransport(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            body = responses_queue.pop(0)
            return httpx.Response(200, content=body, headers={"content-type": "application/json"})

    http_client = httpx.AsyncClient(transport=_FixtureTransport())
    openai_client = openai_lib.AsyncOpenAI(api_key="test-key", http_client=http_client)

    from macro_foundry.agent.llm_openai import make_openai_llm_callable, make_openai_reviewer_callable

    role_configs = default_role_configs()

    research_llm = make_openai_llm_callable(
        role_configs[AgentRole.RESEARCHER], ResearchOutput, client=openai_client
    )
    draft_llm = make_openai_llm_callable(
        role_configs[AgentRole.PROPOSAL_DRAFTER], DraftOutput, client=openai_client
    )
    governance_llm = make_openai_reviewer_callable(
        role_configs[AgentRole.GOVERNANCE_REVIEWER], ReviewerOutput, client=openai_client
    )
    data_correctness_llm = make_openai_reviewer_callable(
        role_configs[AgentRole.DATA_CORRECTNESS_REVIEWER], ReviewerOutput, client=openai_client
    )

    async def _approval_llm(_state: dict[str, Any]) -> dict[str, Any]:
        return {}

    async def _approve_picker(options: list[str], *_: Any) -> str:
        return "approve"

    async def _config_only(_: str) -> str:
        return "config_only"

    async def _empty_cohorts(_: list[dict[str, Any]]) -> dict[str, Any]:
        return {"cohort_a": [], "cohort_b": [], "cohort_c": []}

    from macro_foundry.agent.channel import ChannelEvent, ChannelPrompt, ChannelResponse

    class _SilentChannel:
        async def emit(self, event: ChannelEvent) -> None:
            pass

        async def prompt(self, prompt: ChannelPrompt) -> ChannelResponse:
            return ChannelResponse(text="")

    class _StubWriteTools:
        async def propose_create_series(self, args: Any) -> dict[str, Any]:
            return {
                "proposal_id": "00000000-0000-0000-0000-000000000001",
                "item_id": "00000000-0000-0000-0000-000000000002",
                "series_id": "00000000-0000-0000-0000-000000000003",
                "family_id": "00000000-0000-0000-0000-000000000004",
                "concept_id": "00000000-0000-0000-0000-000000000005",
                "feed_id": "00000000-0000-0000-0000-000000000006",
            }

        async def record_suggest_human_apply(self, args: Any) -> dict[str, Any]:
            return {}

        async def apply_credential_gap_resolutions(self, args: Any) -> dict[str, Any]:
            return {}

        async def trigger_feed_execution(self, args: Any) -> dict[str, Any]:
            return {"run_log_id": "stub-run"}

    class _StubRunLogs:
        async def get_ingestion_run_log(self, run_log_id: str) -> dict[str, Any]:
            return {
                "run_log_id": run_log_id,
                "status": "success",
                "rows_fetched": 5,
                "rows_inserted": 5,
                "rows_skipped": 0,
                "diagnostics": {},
                "warnings": [],
            }

    class _StubTestReviewer:
        async def __call__(self, review_input: dict[str, Any]) -> dict[str, Any]:
            return {"summary": "First run passed."}

    class _StubPackageStore:
        async def save_onboarding_package(self, package: dict[str, Any]) -> dict[str, Any]:
            return {"package_id": "pkg-test"}

    graph = build_onboarding_graph(
        checkpointer=MemorySaver(),
        research_llm=research_llm,
        cohort_lookup=_empty_cohorts,
        extraction_mode_classifier=_config_only,
        draft_llm=draft_llm,
        governance_llm=governance_llm,
        data_correctness_llm=data_correctness_llm,
        approval_llm=_approval_llm,
        gate_1_picker=_approve_picker,
        channel=_SilentChannel(),
        write_tools=_StubWriteTools(),
        run_logs=_StubRunLogs(),
        test_reviewer=_StubTestReviewer(),
        package_store=_StubPackageStore(),
        role_configs=role_configs,
        registry=SkillRegistry({}),
    )

    result = await graph.ainvoke(
        {"pending_input": "Onboard FRED CPI for issue-57 smoke"},
        {"configurable": {"thread_id": "issue-57-openai-smoke"}},
    )

    # The graph ran through the real OpenAI provider path and recorded llm_calls
    llm_calls = result.get("llm_calls", [])
    assert len(llm_calls) >= 1, "Expected at least one llm_calls record from the OpenAI provider"
    first_call = llm_calls[0]
    assert first_call["prompt_tokens"] == 50
    assert first_call["completion_tokens"] == 30
    assert first_call["provider"] == "openai"
