"""CLI coverage for the gated onboarding shell."""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from langgraph.checkpoint.memory import InMemorySaver

from macro_foundry.agent.channel import ChannelEvent, ChannelPrompt, ChannelResponse
from macro_foundry.agent.checkpoint import psycopg_langgraph_url
from macro_foundry.agent.onboarding import OnboardingResult, SessionRuntimeConfig
from macro_foundry.agent.onboarding import run_onboarding_session
from macro_foundry.agent.roles import AgentRole, RoleOverride
from macro_foundry.cli import app
from macro_foundry.db import EnvTarget

runner = CliRunner()


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
    first_channel = FakeChannel(["hello", "/save"])

    first_result = await run_onboarding_session(
        target=EnvTarget.DEV,
        resume_session_id=None,
        channel=first_channel,
        checkpointer=checkpointer,
        session_id_factory=lambda: "friendly-session",
    )

    assert first_result == OnboardingResult(session_id="friendly-session", saved=True)
    assert [event.text for event in first_channel.events] == [
        "hello-world onboarding session friendly-session",
        "hello-world: hello",
        "session friendly-session saved",
    ]

    resumed_channel = FakeChannel(["again", "/save"])
    resumed_result = await run_onboarding_session(
        target=EnvTarget.DEV,
        resume_session_id="friendly-session",
        channel=resumed_channel,
        checkpointer=checkpointer,
    )

    assert resumed_result == OnboardingResult(session_id="friendly-session", saved=True)
    assert [event.text for event in resumed_channel.events] == [
        "hello-world onboarding session friendly-session",
        "hello-world: hello",
        "hello-world: again",
        "session friendly-session saved",
    ]


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

    monkeypatch.setattr(
        "macro_foundry.cli.onboard.run_onboarding_session",
        fake_run_onboarding_session,
    )

    result = runner.invoke(app, ["onboard", "--cost-cap", "2.50"])

    assert result.exit_code == 0
    assert captured["runtime_config"] == SessionRuntimeConfig(max_session_cost_usd=2.50)


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
