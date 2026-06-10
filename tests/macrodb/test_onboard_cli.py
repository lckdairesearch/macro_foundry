"""CLI coverage for the gated onboarding shell."""

from __future__ import annotations

from typing import Any

import pytest
from typer.testing import CliRunner

from langgraph.checkpoint.memory import InMemorySaver

from macro_foundry.agent.channel import ChannelEvent, ChannelPrompt, ChannelResponse
from macro_foundry.agent.checkpoint import psycopg_langgraph_url
from macro_foundry.agent.onboarding import OnboardingGraphDependencies, OnboardingResult, SessionRuntimeConfig
from macro_foundry.agent.onboarding import run_onboarding_session
from macro_foundry.agent.roles import AgentRole, RoleOverride
from macro_foundry.agent.skills import SkillRegistry
from macro_foundry.cli import app
from macro_foundry.db import EnvTarget

runner = CliRunner()


class _FakeGraphWriteTools:
    async def propose_create_series(self, args: Any) -> dict[str, Any]:
        return {
            "proposal_id": "aaaaaaaa-0000-0000-0000-000000000001",
            "item_id": "aaaaaaaa-0000-0000-0000-000000000002",
            "series_id": "aaaaaaaa-0000-0000-0000-000000000003",
            "family_id": "aaaaaaaa-0000-0000-0000-000000000004",
            "concept_id": "aaaaaaaa-0000-0000-0000-000000000005",
            "feed_id": "aaaaaaaa-0000-0000-0000-000000000006",
        }

    async def record_suggest_human_apply(self, args: Any) -> dict[str, Any]:
        return {"proposal_id": "aaaaaaaa-0000-0000-0000-000000000001", "item_ids": []}

    async def apply_credential_gap_resolutions(self, args: Any) -> dict[str, Any]:
        return {"applied": True}

    async def trigger_feed_execution(self, args: Any) -> dict[str, Any]:
        return {
            "feed_id": "aaaaaaaa-0000-0000-0000-000000000006",
            "run_log_id": "aaaaaaaa-0000-0000-0000-000000000007",
            "status": "success",
        }


class _FakeGraphRunLogs:
    async def get_ingestion_run_log(self, run_log_id: str) -> dict[str, Any]:
        return {
            "run_log_id": run_log_id,
            "status": "success",
            "rows_fetched": 1,
            "rows_inserted": 1,
            "rows_skipped": 0,
            "diagnostics": {},
            "warnings": [],
        }


class _FakeGraphPackageStore:
    async def save_onboarding_package(self, package: dict[str, Any]) -> dict[str, Any]:
        return {"package_id": "pkg-test"}


def _llm_usage(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        **payload,
        "prompt_tokens": 1,
        "completion_tokens": 1,
        "total_tokens": 2,
        "cost_estimate_usd": 0.0,
        "latency_ms": 1,
    }


def _fake_graph_dependencies() -> OnboardingGraphDependencies:
    async def research_llm(_messages: list[dict[str, str]]) -> dict[str, Any]:
        return _llm_usage(
            {
                "source_summary": "FRED provides CPI observations through a JSON API.",
                "existing_catalog_hits": [],
                "ambiguity_flags": [],
                "credential_gap_proposals": [],
            }
        )

    async def cohort_lookup(_catalog_hits: list[dict[str, Any]]) -> dict[str, Any]:
        return {"cohort_a": [], "cohort_b": [], "cohort_c": []}

    async def classify(_source_summary: str) -> str:
        return "config_only"

    async def draft_llm(_messages: list[dict[str, str]]) -> dict[str, Any]:
        return _llm_usage(
            {
                "proposal": {
                    "concept": {"action": "new", "code": "CLI_CPI", "name": "CLI CPI"},
                    "family": {
                        "action": "new",
                        "code": "CLI_US_CPI",
                        "name": "CLI US CPI",
                        "concept_code": "CLI_CPI",
                        "geography_code": "USA",
                    },
                    "series": {
                        "action": "new",
                        "code": "CLI_US_CPI_M",
                        "name": "CLI US CPI Monthly",
                        "frequency": "M",
                        "measure": "level",
                        "unit_kind": "index",
                        "temporal_stock_flow": "index",
                        "unit_scale": "one",
                        "seasonal_adjustment": "NSA",
                    },
                    "source": {"provider_name": "USA FRED", "external_code": "CPIAUCNS"},
                    "feed": {
                        "selector_type": "json_path",
                        "cron_schedule": "0 14 * * 5",
                        "feed_method": "api",
                    },
                    "family_member": {"variant": "Headline NSA"},
                },
                "enum_gap_proposals": [],
                "harmonisation_items": [],
                "suggest_human_apply": [],
            }
        )

    async def reviewer_llm(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return _llm_usage({"findings": [], "bounce_to_drafter": False})

    async def approval_llm(_state: dict[str, Any]) -> dict[str, Any]:
        return {}

    async def picker(options: list[str], *_args: Any) -> str:
        assert "approve" in options
        return "approve"

    async def test_reviewer(_review_input: dict[str, Any]) -> dict[str, Any]:
        return {"summary": "ok"}

    return OnboardingGraphDependencies(
        research_llm=research_llm,
        cohort_lookup=cohort_lookup,
        extraction_mode_classifier=classify,
        draft_llm=draft_llm,
        governance_llm=reviewer_llm,
        data_correctness_llm=reviewer_llm,
        approval_llm=approval_llm,
        gate_1_picker=picker,
        write_tools=_FakeGraphWriteTools(),
        run_logs=_FakeGraphRunLogs(),
        test_reviewer=test_reviewer,
        package_store=_FakeGraphPackageStore(),
        registry=SkillRegistry({}),
    )


def _patch_production_deps(monkeypatch: pytest.MonkeyPatch) -> None:
    """Patch build_production_dependencies and DB session creation for CLI unit tests.

    These patches allow CLI argument-parsing tests to reach run_onboarding_session
    without needing a real OpenAI key or DB connection.
    """
    from unittest.mock import AsyncMock, MagicMock

    from macro_foundry.agent.onboarding import OnboardingGraphDependencies
    from macro_foundry.agent.skills import SkillRegistry

    async def _stub_llm(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {}

    class _StubWriteTools:
        async def propose_create_series(self, args: Any) -> dict[str, Any]: return {}
        async def record_suggest_human_apply(self, args: Any) -> dict[str, Any]: return {}
        async def apply_credential_gap_resolutions(self, args: Any) -> dict[str, Any]: return {}
        async def trigger_feed_execution(self, args: Any) -> dict[str, Any]: return {}

    class _StubRunLogs:
        async def get_ingestion_run_log(self, run_log_id: str) -> dict[str, Any]: return {}

    class _StubPackageStore:
        async def save_onboarding_package(self, package: Any) -> dict[str, Any]: return {}

    stub_deps = OnboardingGraphDependencies(
        research_llm=_stub_llm,
        cohort_lookup=_stub_llm,
        extraction_mode_classifier=_stub_llm,
        draft_llm=_stub_llm,
        governance_llm=_stub_llm,
        data_correctness_llm=_stub_llm,
        approval_llm=_stub_llm,
        gate_1_picker=_stub_llm,
        write_tools=_StubWriteTools(),
        run_logs=_StubRunLogs(),
        test_reviewer=_stub_llm,
        package_store=_StubPackageStore(),
        registry=SkillRegistry({}),
    )
    monkeypatch.setattr(
        "macro_foundry.cli.onboard.build_production_dependencies",
        lambda *_args, **_kwargs: stub_deps,
    )

    # Stub out the DB session creation so no real DB connection is attempted.
    mock_session = AsyncMock()
    mock_factory = MagicMock()
    mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)
    monkeypatch.setattr(
        "macro_foundry.cli.onboard.create_session_factory",
        lambda *_args, **_kwargs: mock_factory,
    )
    monkeypatch.setattr(
        "macro_foundry.cli.onboard.create_async_engine_for_url",
        lambda *_args, **_kwargs: MagicMock(),
    )
    monkeypatch.setattr(
        "macro_foundry.cli.onboard.database_url_for_env_target",
        lambda *_args, **_kwargs: "postgresql+psycopg://stub",
    )


@pytest.mark.no_db
def test_onboard_cli_starts_session_with_allowed_target(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_run_onboarding_session(
        *,
        target: EnvTarget,
        resume_session_id: str | None,
        **_: object,
    ) -> OnboardingResult:
        assert target is EnvTarget.DEV
        assert resume_session_id is None
        return OnboardingResult(session_id="onboard-demo", saved=True)

    _patch_production_deps(monkeypatch)
    monkeypatch.setattr(
        "macro_foundry.cli.onboard.run_onboarding_session",
        fake_run_onboarding_session,
    )

    result = runner.invoke(app, ["onboard", "--target", "dev"])

    assert result.exit_code == 0
    assert "session_id=onboard-demo saved=true" in result.output


@pytest.mark.no_db
def test_onboard_cli_passes_role_model_overrides(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_run_onboarding_session(
        *,
        target: EnvTarget,
        resume_session_id: str | None,
        role_config_overrides: dict[AgentRole, RoleOverride],
        **_: object,
    ) -> OnboardingResult:
        assert target is EnvTarget.STAGING
        assert resume_session_id is None
        assert role_config_overrides == {
            AgentRole.RESEARCHER: RoleOverride(default_model="gpt-fast"),
            AgentRole.GOVERNANCE_REVIEWER: RoleOverride(deep_model="gpt-code-review"),
        }
        return OnboardingResult(session_id="onboard-demo", saved=True)

    _patch_production_deps(monkeypatch)
    monkeypatch.setattr(
        "macro_foundry.cli.onboard.run_onboarding_session",
        fake_run_onboarding_session,
    )

    result = runner.invoke(
        app,
        [
            "onboard",
            "--model",
            "researcher=gpt-fast",
            "--deep-model",
            "governance_reviewer=gpt-code-review",
        ],
    )

    assert result.exit_code == 0


@pytest.mark.no_db
@pytest.mark.parametrize("target", ["prod", "test"])
def test_onboard_cli_rejects_non_onboarding_targets(target: str) -> None:
    result = runner.invoke(app, ["onboard", "--target", target])

    assert result.exit_code == 2


@pytest.mark.no_db
def test_postgres_checkpointer_url_targets_langgraph_schema() -> None:
    conn_string = psycopg_langgraph_url(
        "postgresql+psycopg://macrodb_app:secret@example.com:5432/macrodb_staging",
    )

    assert conn_string == (
        "postgresql://macrodb_app:secret@example.com:5432/macrodb_staging"
        "?options=-c%20search_path%3Dlanggraph"
    )


class FakeChannel:
    def __init__(self, responses: list[str]) -> None:
        self.responses = responses
        self.events: list[ChannelEvent] = []
        self.prompts: list[ChannelPrompt] = []

    async def emit(self, event: ChannelEvent) -> None:
        self.events.append(event)

    async def prompt(self, prompt: ChannelPrompt) -> ChannelResponse:
        self.prompts.append(prompt)
        return ChannelResponse(text=self.responses.pop(0))


@pytest.mark.no_db
@pytest.mark.asyncio
async def test_onboard_session_saves_and_resumes_with_fake_channel() -> None:
    checkpointer = InMemorySaver()
    first_channel = FakeChannel(["Onboard FRED CPI", "/save"])
    runtime_config = SessionRuntimeConfig(graph_dependencies=_fake_graph_dependencies())

    first_result = await run_onboarding_session(
        target=EnvTarget.DEV,
        resume_session_id=None,
        channel=first_channel,
        checkpointer=checkpointer,
        session_id_factory=lambda: "friendly-session",
        runtime_config=runtime_config,
    )

    assert first_result == OnboardingResult(session_id="friendly-session", saved=True)
    first_events = [event.text for event in first_channel.events]
    assert first_events[0] == "onboarding session friendly-session"
    assert "Gate 1 Approval" in first_events[1]
    assert first_events[2] == "onboarding_package status=test-approved package_id=pkg-test"
    assert first_events[3] == "session friendly-session saved"

    resumed_channel = FakeChannel(["Onboard FRED CPI again", "/save"])
    resumed_result = await run_onboarding_session(
        target=EnvTarget.DEV,
        resume_session_id="friendly-session",
        channel=resumed_channel,
        checkpointer=checkpointer,
        runtime_config=runtime_config,
    )

    assert resumed_result == OnboardingResult(session_id="friendly-session", saved=True)
    resumed_events = [event.text for event in resumed_channel.events]
    assert resumed_events[0] == "onboarding session friendly-session"
    assert "Gate 1 Approval" in resumed_events[1]
    assert resumed_events[2] == "onboarding_package status=test-approved package_id=pkg-test"
    assert resumed_events[3] == "session friendly-session saved"


@pytest.mark.no_db
def test_onboard_cli_accepts_cost_cap_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    async def fake_run_onboarding_session(
        *,
        target: EnvTarget,
        resume_session_id: str | None,
        runtime_config: SessionRuntimeConfig | None = None,
        **_: object,
    ) -> OnboardingResult:
        captured["runtime_config"] = runtime_config
        return OnboardingResult(session_id="onboard-cost-test", saved=True)

    _patch_production_deps(monkeypatch)
    monkeypatch.setattr(
        "macro_foundry.cli.onboard.run_onboarding_session",
        fake_run_onboarding_session,
    )

    result = runner.invoke(app, ["onboard", "--cost-cap", "2.50"])

    assert result.exit_code == 0
    assert captured["runtime_config"].max_session_cost_usd == 2.50
    assert captured["runtime_config"].graph_dependencies is not None


@pytest.mark.no_db
@pytest.mark.asyncio
async def test_cost_cap_aborts_session_when_exceeded() -> None:
    checkpointer = InMemorySaver()
    channel = FakeChannel(["/save"])

    result = await run_onboarding_session(
        target=EnvTarget.DEV,
        resume_session_id=None,
        channel=channel,
        checkpointer=checkpointer,
        session_id_factory=lambda: "cost-cap-session",
        runtime_config=SessionRuntimeConfig(max_session_cost_usd=0.0),
    )

    assert result.aborted is True
    assert result.abort_reason == "cost_cap_exceeded"


@pytest.mark.no_db
@pytest.mark.asyncio
async def test_concurrency_advisory_warns_when_another_session_exists(
    caplog: pytest.LogCaptureFixture,
) -> None:
    import logging

    checkpointer = InMemorySaver()

    first_channel = FakeChannel(["/save"])
    await run_onboarding_session(
        target=EnvTarget.DEV,
        resume_session_id=None,
        channel=first_channel,
        checkpointer=checkpointer,
        session_id_factory=lambda: "session-alpha",
    )

    second_channel = FakeChannel(["/save"])
    with caplog.at_level(logging.WARNING, logger="macro_foundry.agent.onboarding"):
        await run_onboarding_session(
            target=EnvTarget.DEV,
            resume_session_id=None,
            channel=second_channel,
            checkpointer=checkpointer,
            session_id_factory=lambda: "session-beta",
        )

    assert any("concurrent" in record.message.lower() for record in caplog.records)


@pytest.mark.no_db
@pytest.mark.asyncio
async def test_concurrency_advisory_not_triggered_for_first_session(
    caplog: pytest.LogCaptureFixture,
) -> None:
    import logging

    checkpointer = InMemorySaver()
    channel = FakeChannel(["/save"])

    with caplog.at_level(logging.WARNING, logger="macro_foundry.agent.onboarding"):
        await run_onboarding_session(
            target=EnvTarget.DEV,
            resume_session_id=None,
            channel=channel,
            checkpointer=checkpointer,
            session_id_factory=lambda: "only-session",
        )

    assert not any("concurrent" in record.message.lower() for record in caplog.records)


@pytest.mark.no_db
@pytest.mark.asyncio
async def test_cost_cap_not_triggered_when_cost_below_cap() -> None:
    checkpointer = InMemorySaver()
    channel = FakeChannel(["/save"])

    result = await run_onboarding_session(
        target=EnvTarget.DEV,
        resume_session_id=None,
        channel=channel,
        checkpointer=checkpointer,
        session_id_factory=lambda: "cost-ok-session",
        runtime_config=SessionRuntimeConfig(max_session_cost_usd=100.0),
    )

    assert result.aborted is False
    assert result.session_id == "cost-ok-session"
