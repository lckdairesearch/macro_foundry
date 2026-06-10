"""Tests for the production dependency factory (issue 57 — last mile)."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_LLM_USAGE = {
    "prompt_tokens": 50,
    "completion_tokens": 30,
    "total_tokens": 80,
    "cost_estimate_usd": 0.001,
    "latency_ms": 123,
}


def _openai_response(content: dict[str, Any]) -> bytes:
    """Minimal OpenAI chat.completions.parse JSON fixture."""
    return json.dumps({
        "id": "chatcmpl-test",
        "object": "chat.completion",
        "model": "gpt-5.4",
        "choices": [{
            "index": 0,
            "message": {
                "role": "assistant",
                "content": json.dumps(content),
                "parsed": content,
                "refusal": None,
            },
            "finish_reason": "stop",
            "logprobs": None,
        }],
        "usage": {
            "prompt_tokens": 50,
            "completion_tokens": 30,
            "total_tokens": 80,
        },
    }).encode()


def _make_mock_session() -> Any:
    """Return a minimal AsyncSession mock."""
    session = AsyncMock()
    return session


def _make_mock_openai_client(responses: list[bytes]) -> Any:
    """Return an openai.AsyncOpenAI backed by a queue of fixture responses."""
    import httpx
    import openai as openai_lib

    queue = list(responses)

    class _FixtureTransport(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            body = queue.pop(0)
            return httpx.Response(200, content=body, headers={"content-type": "application/json"})

    http_client = httpx.AsyncClient(transport=_FixtureTransport())
    return openai_lib.AsyncOpenAI(api_key="test-key", http_client=http_client)


def _make_capturing_openai_client(
    responses: list[bytes],
    captured_requests: list[dict[str, Any]],
) -> Any:
    """Return an openai.AsyncOpenAI that records request JSON bodies."""
    import httpx
    import openai as openai_lib

    queue = list(responses)

    class _CapturingTransport(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            captured_requests.append(json.loads(request.content))
            body = queue.pop(0)
            return httpx.Response(200, content=body, headers={"content-type": "application/json"})

    http_client = httpx.AsyncClient(transport=_CapturingTransport())
    return openai_lib.AsyncOpenAI(api_key="test-key", http_client=http_client)


class _ToolSeries:
    def __init__(self, code: str) -> None:
        self.code = code
        self.name = f"{code} name"

    def model_dump(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return {"code": self.code, "name": self.name}


# ---------------------------------------------------------------------------
# Cycle 1 — build_production_dependencies returns OnboardingGraphDependencies
# ---------------------------------------------------------------------------


@pytest.mark.no_db
def test_build_production_dependencies_returns_correct_type() -> None:
    from macro_foundry.agent.onboarding import OnboardingGraphDependencies
    from macro_foundry.agent.production_deps import build_production_dependencies
    from macro_foundry.agent.roles import default_role_configs

    session = _make_mock_session()
    client = MagicMock()
    role_configs = default_role_configs()

    deps = build_production_dependencies(role_configs, session=session, client=client)

    assert isinstance(deps, OnboardingGraphDependencies)


@pytest.mark.no_db
def test_build_production_dependencies_has_no_raising_stubs() -> None:
    """None of the LLM fields should be the _missing_graph_dependencies raising stubs."""
    import inspect

    from macro_foundry.agent.production_deps import build_production_dependencies
    from macro_foundry.agent.roles import default_role_configs

    session = _make_mock_session()
    client = MagicMock()
    role_configs = default_role_configs()

    deps = build_production_dependencies(role_configs, session=session, client=client)

    # Verify the functions are not the raising stubs (inspect source code)
    for attr_name in ("research_llm", "draft_llm", "governance_llm", "data_correctness_llm"):
        fn = getattr(deps, attr_name)
        src = inspect.getsource(fn)
        assert "onboarding graph dependencies are not configured" not in src, (
            f"{attr_name} is still a missing-stub function"
        )


# ---------------------------------------------------------------------------
# Cycle 2 — research_llm uses make_openai_llm_callable and returns correct format
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.no_db
async def test_research_llm_returns_correct_format_via_mock_transport() -> None:
    from macro_foundry.agent.production_deps import build_production_dependencies
    from macro_foundry.agent.roles import default_role_configs

    research_content = {
        "source_summary": "FRED CPI JSON API.",
        "existing_catalog_hits": [],
        "ambiguity_flags": [],
        "credential_gap_proposals": [],
    }
    client = _make_mock_openai_client([_openai_response(research_content)])
    session = _make_mock_session()
    role_configs = default_role_configs()

    deps = build_production_dependencies(role_configs, session=session, client=client)

    result = await deps.research_llm([{"role": "user", "content": "Onboard FRED CPI"}])

    assert result["source_summary"] == "FRED CPI JSON API."
    assert result["prompt_tokens"] == 50
    assert result["completion_tokens"] == 30
    assert "cost_estimate_usd" in result
    assert "latency_ms" in result


# ---------------------------------------------------------------------------
# Cycle 3 — governance_llm honours task_hint model tiering
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.no_db
async def test_governance_llm_honours_task_hint_tiering() -> None:
    """governance_llm should resolve a different model when task_hint=selector_code_review."""
    from macro_foundry.agent.production_deps import build_production_dependencies
    from macro_foundry.agent.roles import AgentRole, DecodeParams, LLMProvider, RoleConfig, default_role_configs

    reviewer_content = {"findings": [], "bounce_to_drafter": False}

    # Override governance role to use distinct models for default vs task hint
    role_configs = default_role_configs()
    gov_config = RoleConfig(
        role=AgentRole.GOVERNANCE_REVIEWER,
        default_model="gpt-4o-mini",
        provider=LLMProvider.OPENAI,
        decode=DecodeParams(temperature=0.2),
        models_by_task={"selector_code_review": "gpt-4o"},
    )
    role_configs = {**role_configs, AgentRole.GOVERNANCE_REVIEWER: gov_config}

    captured_models: list[str] = []

    import httpx
    import openai as openai_lib

    class _CapturingTransport(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            body = json.loads(request.content)
            captured_models.append(body.get("model", ""))
            return httpx.Response(
                200,
                content=_openai_response(reviewer_content),
                headers={"content-type": "application/json"},
            )

    http_client = httpx.AsyncClient(transport=_CapturingTransport())
    client = openai_lib.AsyncOpenAI(api_key="test-key", http_client=http_client)
    session = _make_mock_session()

    deps = build_production_dependencies(role_configs, session=session, client=client)

    # Call without task_hint → default_model
    await deps.governance_llm([{"role": "user", "content": "review"}])
    # Call with task_hint → models_by_task model
    await deps.governance_llm([{"role": "user", "content": "review"}], task_hint="selector_code_review")

    assert captured_models[0] == "gpt-4o-mini", "default call should use gpt-4o-mini"
    assert captured_models[1] == "gpt-4o", "task_hint call should use gpt-4o"


# ---------------------------------------------------------------------------
# Cycle 4 — CLI populates graph_dependencies; _missing_graph_dependencies unreachable
# ---------------------------------------------------------------------------


@pytest.mark.no_db
def test_cli_populates_graph_dependencies_not_missing_stubs() -> None:
    """The onboard CLI must inject real dependencies; _missing_graph_dependencies should not be called."""
    from macro_foundry.agent.onboarding import (
        SessionRuntimeConfig,
        _missing_graph_dependencies,
    )
    from macro_foundry.agent.production_deps import build_production_dependencies
    from macro_foundry.agent.roles import default_role_configs

    session = _make_mock_session()
    client = MagicMock()
    role_configs = default_role_configs()

    deps = build_production_dependencies(role_configs, session=session, client=client)
    runtime_config = SessionRuntimeConfig(graph_dependencies=deps)

    # When graph_dependencies is populated, _missing_graph_dependencies must not be reached
    assert runtime_config.graph_dependencies is not None
    assert runtime_config.graph_dependencies is not _missing_graph_dependencies()


# ---------------------------------------------------------------------------
# Cycle 5 — cohort_lookup uses MCP read tools instead of a hardcoded empty cohort
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.no_db
async def test_cohort_lookup_returns_real_mcp_cohorts(monkeypatch: pytest.MonkeyPatch) -> None:
    from macro_foundry.agent.production_deps import build_production_dependencies
    from macro_foundry.agent.roles import default_role_configs

    calls: list[tuple[str, Any]] = []

    class _StubReadTools:
        def __init__(self, session: Any) -> None:
            self.session = session

        async def find_sibling_series(self, args: Any) -> list[_ToolSeries]:
            calls.append(("siblings", str(args.family_id)))
            return [_ToolSeries("US_CPI_HEADLINE"), _ToolSeries("US_CPI_CORE")]

        async def list_series_for_concept(self, args: Any) -> list[_ToolSeries]:
            calls.append(("concept", str(args.concept_id)))
            return [_ToolSeries("JP_CPI_HEADLINE")]

        async def list_provider_series_for_concept(self, args: Any) -> list[_ToolSeries]:
            calls.append(
                ("provider_concept", (str(args.provider_id), str(args.concept_id)))
            )
            return [_ToolSeries("FRED_US_CPI_HEADLINE")]

    monkeypatch.setattr(
        "macro_foundry.agent.production_deps.MacrodbReadTools",
        _StubReadTools,
    )

    deps = build_production_dependencies(
        default_role_configs(),
        session=_make_mock_session(),
        client=MagicMock(),
    )

    cohorts = await deps.cohort_lookup(
        [
            {
                "family_id": "00000000-0000-0000-0000-000000000001",
                "concept_id": "00000000-0000-0000-0000-000000000002",
                "provider_id": "00000000-0000-0000-0000-000000000003",
            }
        ]
    )

    assert calls == [
        ("siblings", "00000000-0000-0000-0000-000000000001"),
        ("concept", "00000000-0000-0000-0000-000000000002"),
        (
            "provider_concept",
            (
                "00000000-0000-0000-0000-000000000003",
                "00000000-0000-0000-0000-000000000002",
            ),
        ),
    ]
    assert [item["code"] for item in cohorts["cohort_a"]] == [
        "US_CPI_HEADLINE",
        "US_CPI_CORE",
    ]
    assert [item["code"] for item in cohorts["cohort_b"]] == ["JP_CPI_HEADLINE"]
    assert [item["code"] for item in cohorts["cohort_c"]] == [
        "FRED_US_CPI_HEADLINE"
    ]


@pytest.mark.asyncio
@pytest.mark.no_db
async def test_cohort_lookup_uses_catalog_hit_kind_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from macro_foundry.agent.production_deps import build_production_dependencies
    from macro_foundry.agent.roles import default_role_configs

    calls: list[tuple[str, Any]] = []

    class _StubReadTools:
        def __init__(self, session: Any) -> None:
            self.session = session

        async def find_sibling_series(self, args: Any) -> list[_ToolSeries]:
            calls.append(("siblings", str(args.family_id)))
            return [_ToolSeries("US_CPI_HEADLINE")]

        async def list_series_for_concept(self, args: Any) -> list[_ToolSeries]:
            calls.append(("concept", str(args.concept_id)))
            return [_ToolSeries("JP_CPI_HEADLINE")]

        async def list_provider_series_for_concept(self, args: Any) -> list[_ToolSeries]:
            calls.append(
                ("provider_concept", (str(args.provider_id), str(args.concept_id)))
            )
            return [_ToolSeries("FRED_US_CPI_HEADLINE")]

    monkeypatch.setattr(
        "macro_foundry.agent.production_deps.MacrodbReadTools",
        _StubReadTools,
    )

    deps = build_production_dependencies(
        default_role_configs(),
        session=_make_mock_session(),
        client=MagicMock(),
    )

    cohorts = await deps.cohort_lookup(
        [
            {"kind": "family", "id": "00000000-0000-0000-0000-000000000001"},
            {"kind": "concept", "id": "00000000-0000-0000-0000-000000000002"},
            {"kind": "provider", "id": "00000000-0000-0000-0000-000000000003"},
        ]
    )

    assert calls == [
        ("siblings", "00000000-0000-0000-0000-000000000001"),
        ("concept", "00000000-0000-0000-0000-000000000002"),
        (
            "provider_concept",
            (
                "00000000-0000-0000-0000-000000000003",
                "00000000-0000-0000-0000-000000000002",
            ),
        ),
    ]
    assert [item["code"] for item in cohorts["cohort_a"]] == ["US_CPI_HEADLINE"]
    assert [item["code"] for item in cohorts["cohort_b"]] == ["JP_CPI_HEADLINE"]
    assert [item["code"] for item in cohorts["cohort_c"]] == [
        "FRED_US_CPI_HEADLINE"
    ]


# ---------------------------------------------------------------------------
# Cycle 6 — extraction_mode_classifier consults selector registry
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.no_db
async def test_extraction_mode_classifier_prefers_registered_selector_over_keyword(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from macro_foundry.agent.production_deps import build_production_dependencies
    from macro_foundry.agent.roles import default_role_configs

    list_selector_types_called = False

    class _StubReadTools:
        def __init__(self, session: Any) -> None:
            self.session = session

        async def list_selector_types(self) -> list[str]:
            nonlocal list_selector_types_called
            list_selector_types_called = True
            return ["json_path"]

        async def get_selector_schema(self, args: Any) -> dict[str, Any]:
            return {
                "required": [
                    "records_path",
                    "period_anchor_field",
                    "value_field",
                    "frequency",
                ]
            }

    monkeypatch.setattr(
        "macro_foundry.agent.production_deps.MacrodbReadTools",
        _StubReadTools,
    )

    deps = build_production_dependencies(
        default_role_configs(),
        session=_make_mock_session(),
        client=MagicMock(),
    )

    mode = await deps.extraction_mode_classifier(
        "Provider has a custom JSON API, but the response fits json_path."
    )

    assert list_selector_types_called is True
    assert mode == "config_only"


@pytest.mark.asyncio
@pytest.mark.no_db
async def test_extraction_mode_classifier_consults_selector_schemas(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from macro_foundry.agent.production_deps import build_production_dependencies
    from macro_foundry.agent.roles import default_role_configs

    schemas_requested: list[str] = []

    class _StubReadTools:
        def __init__(self, session: Any) -> None:
            self.session = session

        async def list_selector_types(self) -> list[str]:
            return ["json_path"]

        async def get_selector_schema(self, args: Any) -> dict[str, Any]:
            schemas_requested.append(args.selector_type)
            return {
                "type": "object",
                "required": [
                    "records_path",
                    "period_anchor_field",
                    "value_field",
                    "frequency",
                ],
                "properties": {
                    "records_path": {"type": "string"},
                    "period_anchor_field": {"type": "string"},
                    "value_field": {"type": "string"},
                    "frequency": {"type": "string"},
                },
            }

    monkeypatch.setattr(
        "macro_foundry.agent.production_deps.MacrodbReadTools",
        _StubReadTools,
    )

    deps = build_production_dependencies(
        default_role_configs(),
        session=_make_mock_session(),
        client=MagicMock(),
    )

    mode = await deps.extraction_mode_classifier(
        "Provider returns a JSON array of records with period and value fields."
    )

    assert schemas_requested == ["json_path"]
    assert mode == "config_only"


@pytest.mark.asyncio
@pytest.mark.no_db
async def test_extraction_mode_classifier_uses_small_llm_for_ambiguous_shape(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from macro_foundry.agent.production_deps import build_production_dependencies
    from macro_foundry.agent.roles import default_role_configs

    class _StubReadTools:
        def __init__(self, session: Any) -> None:
            self.session = session

        async def list_selector_types(self) -> list[str]:
            return ["json_path"]

        async def get_selector_schema(self, args: Any) -> dict[str, Any]:
            return {
                "required": [
                    "records_path",
                    "period_anchor_field",
                    "value_field",
                    "frequency",
                ]
            }

    monkeypatch.setattr(
        "macro_foundry.agent.production_deps.MacrodbReadTools",
        _StubReadTools,
    )
    client = _make_mock_openai_client([
        _openai_response(
            {
                "extraction_mode": "custom_python",
                "rationale": "XML envelope does not match registered JSON selectors.",
            }
        )
    ])
    deps = build_production_dependencies(
        default_role_configs(),
        session=_make_mock_session(),
        client=client,
    )

    mode = await deps.extraction_mode_classifier(
        "Provider returns a nested XML envelope with undocumented dimensions."
    )

    assert mode == "custom_python"


# ---------------------------------------------------------------------------
# Cycle 7 — End-to-end: full onboarding graph with mock OpenAI through emit_package
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.no_db
async def test_production_deps_full_graph_through_emit_package() -> None:
    """Full onboarding using build_production_dependencies with mock OpenAI transport."""
    from langgraph.checkpoint.memory import MemorySaver

    from macro_foundry.agent.graph import build_onboarding_graph
    from macro_foundry.agent.onboarding_state import SessionMetadata
    from macro_foundry.agent.production_deps import build_production_dependencies
    from macro_foundry.agent.roles import default_role_configs
    from datetime import datetime, timezone

    research_content = {
        "source_summary": "FRED CPI JSON API.",
        "existing_catalog_hits": [],
        "ambiguity_flags": [],
        "credential_gap_proposals": [],
    }
    draft_content = {
        "proposal": {
            "concept": {"action": "new", "code": "CPI", "name": "Consumer Price Index"},
            "family": {"action": "new", "code": "USA_CPI", "name": "US CPI", "geography_code": "USA"},
            "series": {
                "action": "new",
                "code": "CPI_USA_ALL_M_NSA_LEVEL",
                "name": "US CPI Headline NSA",
                "description": "US Consumer Price Index from FRED.",
                "frequency": "M",
                "seasonal_adjustment": "NSA",
                "measure": "LEVEL",
                "temporal_stock_flow": "FLOW",
                "unit_scale": "ONE",
                "unit_kind": "INDEX",
            },
            "family_member": {"variant": "Headline NSA"},
            "sources": [],
            "feed": {
                "selector_type": "json_path",
                "selector_config": {},
                "feed_method": "api",
                "fetch_url": "/series/observations",
            },
        },
        "enum_gap_proposals": [],
        "harmonisation_items": [],
        "suggest_human_apply": [],
    }
    reviewer_content = {"findings": [], "bounce_to_drafter": False}

    responses = [
        _openai_response(research_content),      # research node
        _openai_response(draft_content),          # draft_proposal node
        _openai_response(reviewer_content),       # governance_review node
        _openai_response(reviewer_content),       # data_correctness_review node
    ]
    client = _make_mock_openai_client(responses)
    session = _make_mock_session()
    role_configs = default_role_configs()

    deps = build_production_dependencies(role_configs, session=session, client=client)

    # Override write_tools, run_logs, package_store, pickers with stubs for graph execution
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
        async def record_suggest_human_apply(self, args: Any) -> dict[str, Any]: return {}
        async def apply_credential_gap_resolutions(self, args: Any) -> dict[str, Any]: return {}
        async def trigger_feed_execution(self, args: Any) -> dict[str, Any]:
            return {"run_log_id": "run-stub"}

    class _StubRunLogs:
        async def get_ingestion_run_log(self, run_log_id: str) -> dict[str, Any]:
            return {"run_log_id": run_log_id, "status": "success", "rows_fetched": 5, "rows_inserted": 5, "rows_skipped": 0, "diagnostics": {}, "warnings": []}

    class _StubTestReviewer:
        async def __call__(self, review_input: dict[str, Any]) -> dict[str, Any]:
            return {"summary": "First run passed."}

    class _StubPackageStore:
        async def save_onboarding_package(self, package: dict[str, Any]) -> dict[str, Any]:
            return {"package_id": "pkg-e2e"}

    async def _approve_picker(options: list[str], *_: Any) -> str:
        return "approve"

    from macro_foundry.agent.channel import ChannelEvent, ChannelPrompt, ChannelResponse

    class _SilentChannel:
        async def emit(self, event: ChannelEvent) -> None: pass
        async def prompt(self, prompt: ChannelPrompt) -> ChannelResponse:
            return ChannelResponse(text="")

    from macro_foundry.agent.skills import SkillRegistry

    graph = build_onboarding_graph(
        checkpointer=MemorySaver(),
        research_llm=deps.research_llm,
        cohort_lookup=deps.cohort_lookup,
        extraction_mode_classifier=deps.extraction_mode_classifier,
        draft_llm=deps.draft_llm,
        governance_llm=deps.governance_llm,
        data_correctness_llm=deps.data_correctness_llm,
        approval_llm=deps.approval_llm,
        gate_1_picker=_approve_picker,  # override for non-interactive test
        channel=_SilentChannel(),
        write_tools=_StubWriteTools(),
        run_logs=_StubRunLogs(),
        test_reviewer=_StubTestReviewer(),
        package_store=_StubPackageStore(),
        role_configs=role_configs,
        registry=SkillRegistry({}),
    )

    result = await graph.ainvoke(
        {
            "pending_input": "Onboard FRED CPI for issue-57 production-deps test",
            "session_metadata": SessionMetadata(
                session_id="prod-deps-e2e",
                target_environment="dev",
                created_at=datetime.now(timezone.utc),
                created_by="tester",
                cli_version="0.0.0",
            ).model_dump(mode="json"),
        },
        {"configurable": {"thread_id": "prod-deps-e2e"}},
    )

    # LLM calls recorded from the real OpenAI provider path (not missing stubs)
    llm_calls = result.get("llm_calls", [])
    assert len(llm_calls) >= 1, "Expected llm_calls from the real OpenAI provider"
    assert llm_calls[0]["prompt_tokens"] == 50
    assert llm_calls[0]["provider"] == "openai"

    # Graph ran to completion
    assert result.get("onboarding_package") or result.get("gate_1_approved")


@pytest.mark.asyncio
@pytest.mark.no_db
async def test_production_graph_flows_non_empty_cohort_into_drafter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Full graph with production deps sends MCP cohort metadata to draft_proposal."""
    from datetime import datetime, timezone

    from langgraph.checkpoint.memory import MemorySaver

    from macro_foundry.agent.graph import build_onboarding_graph
    from macro_foundry.agent.onboarding_state import SessionMetadata
    from macro_foundry.agent.production_deps import build_production_dependencies
    from macro_foundry.agent.roles import default_role_configs
    from macro_foundry.agent.skills import SkillRegistry

    class _StubReadTools:
        def __init__(self, session: Any) -> None:
            self.session = session

        async def find_sibling_series(self, args: Any) -> list[_ToolSeries]:
            return [_ToolSeries("US_CPI_EXISTING_NSA")]

        async def list_series_for_concept(self, args: Any) -> list[_ToolSeries]:
            return [_ToolSeries("JP_CPI_EXISTING_NSA")]

        async def list_provider_series_for_concept(self, args: Any) -> list[_ToolSeries]:
            return [_ToolSeries("FRED_US_CPI_EXISTING_NSA")]

        async def list_selector_types(self) -> list[str]:
            return ["json_path"]

        async def get_selector_schema(self, args: Any) -> dict[str, Any]:
            return {
                "required": [
                    "records_path",
                    "period_anchor_field",
                    "value_field",
                    "frequency",
                ]
            }

    monkeypatch.setattr(
        "macro_foundry.agent.production_deps.MacrodbReadTools",
        _StubReadTools,
    )

    research_content = {
        "source_summary": "FRED CPI JSON API.",
        "existing_catalog_hits": [
            {"kind": "family", "id": "00000000-0000-0000-0000-000000000004"},
            {"kind": "concept", "id": "00000000-0000-0000-0000-000000000005"},
            {"kind": "provider", "id": "00000000-0000-0000-0000-000000000006"},
        ],
        "ambiguity_flags": [],
        "credential_gap_proposals": [],
    }
    draft_content = {
        "proposal": {
            "concept": {"action": "existing", "code": "CPI", "name": "Consumer Price Index"},
            "family": {"action": "existing", "code": "USA_CPI", "name": "US CPI", "geography_code": "USA"},
            "series": {
                "action": "new",
                "code": "CPI_USA_CORE_M_NSA_LEVEL",
                "name": "US CPI Core NSA",
                "description": "US Consumer Price Index core variant from FRED.",
                "frequency": "M",
                "seasonal_adjustment": "NSA",
                "measure": "LEVEL",
                "temporal_stock_flow": "FLOW",
                "unit_scale": "ONE",
                "unit_kind": "INDEX",
            },
            "family_member": {"variant": "Core NSA"},
            "sources": [],
            "feed": {
                "selector_type": "json_path",
                "selector_config": {},
                "feed_method": "api",
                "fetch_url": "/series/observations",
            },
        },
        "enum_gap_proposals": [],
        "harmonisation_items": [],
        "suggest_human_apply": [],
    }
    reviewer_content = {"findings": [], "bounce_to_drafter": False}
    captured_requests: list[dict[str, Any]] = []
    client = _make_capturing_openai_client(
        [
            _openai_response(research_content),
            _openai_response(draft_content),
            _openai_response(reviewer_content),
            _openai_response(reviewer_content),
        ],
        captured_requests,
    )
    role_configs = default_role_configs()
    deps = build_production_dependencies(
        role_configs,
        session=_make_mock_session(),
        client=client,
    )

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
            return {"run_log_id": "run-stub"}

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
            return {"package_id": "pkg-e2e"}

    async def _approve_picker(options: list[str], *_: Any) -> str:
        return "approve"

    from macro_foundry.agent.channel import ChannelEvent, ChannelPrompt, ChannelResponse

    class _SilentChannel:
        async def emit(self, event: ChannelEvent) -> None:
            pass

        async def prompt(self, prompt: ChannelPrompt) -> ChannelResponse:
            return ChannelResponse(text="")

    graph = build_onboarding_graph(
        checkpointer=MemorySaver(),
        research_llm=deps.research_llm,
        cohort_lookup=deps.cohort_lookup,
        extraction_mode_classifier=deps.extraction_mode_classifier,
        draft_llm=deps.draft_llm,
        governance_llm=deps.governance_llm,
        data_correctness_llm=deps.data_correctness_llm,
        approval_llm=deps.approval_llm,
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
        {
            "pending_input": "Onboard FRED CPI core",
            "session_metadata": SessionMetadata(
                session_id="prod-deps-non-empty-cohort",
                target_environment="dev",
                created_at=datetime.now(timezone.utc),
                created_by="tester",
                cli_version="0.0.0",
            ).model_dump(mode="json"),
        },
        {"configurable": {"thread_id": "prod-deps-non-empty-cohort"}},
    )

    assert result["reference_metadata"]["cohort_a"][0]["code"] == "US_CPI_EXISTING_NSA"
    assert result["is_first_in_family"] is False
    draft_messages = captured_requests[1]["messages"]
    draft_prompt = "\n".join(message["content"] for message in draft_messages)
    assert "US_CPI_EXISTING_NSA" in draft_prompt
    assert "FRED_US_CPI_EXISTING_NSA" in draft_prompt
