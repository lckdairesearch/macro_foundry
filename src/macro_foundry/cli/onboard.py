"""`macrodb onboard` command."""

from __future__ import annotations

import asyncio
from typing import Annotated

import typer

from macro_foundry.agent.onboarding import OnboardingResult, OnboardingTarget, SessionRuntimeConfig, run_onboarding_session
from macro_foundry.agent.roles import AgentRole, RoleOverride

from ._app import app


@app.command("onboard")
def onboard(
    target: Annotated[
        OnboardingTarget,
        typer.Option(
            "--target",
            case_sensitive=False,
            help="Target dev or staging. Defaults to staging.",
        ),
    ] = OnboardingTarget.STAGING,
    resume_session_id: Annotated[
        str | None,
        typer.Option("--resume", help="Resume a saved onboarding session."),
    ] = None,
    researcher_model: Annotated[str | None, typer.Option("--researcher-model")] = None,
    researcher_deep_model: Annotated[str | None, typer.Option("--researcher-deep-model")] = None,
    proposal_drafter_model: Annotated[str | None, typer.Option("--proposal-drafter-model")] = None,
    proposal_drafter_deep_model: Annotated[
        str | None,
        typer.Option("--proposal-drafter-deep-model"),
    ] = None,
    script_drafter_model: Annotated[str | None, typer.Option("--script-drafter-model")] = None,
    script_drafter_deep_model: Annotated[str | None, typer.Option("--script-drafter-deep-model")] = None,
    validator_model: Annotated[str | None, typer.Option("--validator-model")] = None,
    validator_deep_model: Annotated[str | None, typer.Option("--validator-deep-model")] = None,
    governance_reviewer_model: Annotated[str | None, typer.Option("--governance-reviewer-model")] = None,
    governance_reviewer_deep_model: Annotated[
        str | None,
        typer.Option("--governance-reviewer-deep-model"),
    ] = None,
    data_correctness_reviewer_model: Annotated[
        str | None,
        typer.Option("--data-correctness-reviewer-model"),
    ] = None,
    data_correctness_reviewer_deep_model: Annotated[
        str | None,
        typer.Option("--data-correctness-reviewer-deep-model"),
    ] = None,
    approval_parser_model: Annotated[str | None, typer.Option("--approval-parser-model")] = None,
    approval_parser_deep_model: Annotated[str | None, typer.Option("--approval-parser-deep-model")] = None,
    test_reviewer_model: Annotated[str | None, typer.Option("--test-reviewer-model")] = None,
    test_reviewer_deep_model: Annotated[str | None, typer.Option("--test-reviewer-deep-model")] = None,
    dangerous_correction_planner_model: Annotated[
        str | None,
        typer.Option("--dangerous-correction-planner-model"),
    ] = None,
    dangerous_correction_planner_deep_model: Annotated[
        str | None,
        typer.Option("--dangerous-correction-planner-deep-model"),
    ] = None,
    max_session_cost_usd: Annotated[
        float | None,
        typer.Option("--max-session-cost-usd", help="Hard cost cap in USD. Aborts if exceeded."),
    ] = None,
) -> None:
    """Open the gated onboarding chat shell."""

    runtime_config = SessionRuntimeConfig(max_session_cost_usd=max_session_cost_usd)

    try:
        result: OnboardingResult = asyncio.run(
            run_onboarding_session(
                target=target,
                resume_session_id=resume_session_id,
                runtime_config=runtime_config,
                **_role_override_kwargs(
                    {
                        AgentRole.RESEARCHER: RoleOverride(researcher_model, researcher_deep_model),
                        AgentRole.PROPOSAL_DRAFTER: RoleOverride(
                            proposal_drafter_model,
                            proposal_drafter_deep_model,
                        ),
                        AgentRole.SCRIPT_DRAFTER: RoleOverride(
                            script_drafter_model,
                            script_drafter_deep_model,
                        ),
                        AgentRole.VALIDATOR: RoleOverride(validator_model, validator_deep_model),
                        AgentRole.GOVERNANCE_REVIEWER: RoleOverride(
                            governance_reviewer_model,
                            governance_reviewer_deep_model,
                        ),
                        AgentRole.DATA_CORRECTNESS_REVIEWER: RoleOverride(
                            data_correctness_reviewer_model,
                            data_correctness_reviewer_deep_model,
                        ),
                        AgentRole.APPROVAL_PARSER: RoleOverride(approval_parser_model, approval_parser_deep_model),
                        AgentRole.TEST_REVIEWER: RoleOverride(test_reviewer_model, test_reviewer_deep_model),
                        AgentRole.DANGEROUS_CORRECTION_PLANNER: RoleOverride(
                            dangerous_correction_planner_model,
                            dangerous_correction_planner_deep_model,
                        ),
                    },
                ),
            ),
        )
    except ValueError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc
    typer.echo(f"session_id={result.session_id} saved={str(result.saved).lower()}")


def _role_override_kwargs(overrides: dict[AgentRole, RoleOverride]) -> dict[str, dict[AgentRole, RoleOverride]]:
    active_overrides = {
        role: override
        for role, override in overrides.items()
        if override.default_model is not None or override.deep_model is not None
    }
    if not active_overrides:
        return {}
    return {"role_config_overrides": active_overrides}
