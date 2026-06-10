"""`macrodb onboard` command."""

from __future__ import annotations

import asyncio
from typing import Annotated

import typer

from macro_foundry.agent.onboarding import OnboardingResult, SessionRuntimeConfig, run_onboarding_session
from macro_foundry.agent.roles import AgentRole, RoleOverride
from macro_foundry.db import EnvTarget

from . import _helpers
from ._app import app

_ONBOARDING_TARGETS = {EnvTarget.DEV, EnvTarget.STAGING}


@app.command("onboard")
@_helpers.cli_error_handler
def onboard(
    target: Annotated[
        EnvTarget,
        typer.Option(
            "--target",
            case_sensitive=False,
            help="Target dev or staging. Defaults to staging.",
        ),
    ] = EnvTarget.STAGING,
    resume_session_id: Annotated[
        str | None,
        typer.Option("--resume", help="Resume a saved onboarding session by session ID."),
    ] = None,
    model: Annotated[
        list[str] | None,
        typer.Option(
            "--model",
            help="Override the default model for a role: ROLE=MODEL (repeatable).",
        ),
    ] = None,
    deep_model: Annotated[
        list[str] | None,
        typer.Option(
            "--deep-model",
            help="Override the deep model for a role: ROLE=MODEL (repeatable).",
        ),
    ] = None,
    cost_cap: Annotated[
        float | None,
        typer.Option("--cost-cap", help="Hard cost cap in USD. Aborts if exceeded."),
    ] = None,
    output_json: Annotated[
        bool,
        typer.Option("--json", help="Emit result as JSON instead of key=value lines."),
    ] = False,
) -> None:
    """Open the gated onboarding chat shell."""

    if target not in _ONBOARDING_TARGETS:
        typer.echo(f"onboard does not support --target {target.value} (allowed: dev, staging)", err=True)
        raise typer.Exit(code=2)

    role_config_overrides = _parse_role_overrides(model or [], deep_model or [])
    runtime_config = SessionRuntimeConfig(max_session_cost_usd=cost_cap)

    result: OnboardingResult = asyncio.run(
        run_onboarding_session(
            target=target,
            resume_session_id=resume_session_id,
            runtime_config=runtime_config,
            **({"role_config_overrides": role_config_overrides} if role_config_overrides else {}),
        ),
    )

    _helpers.print_result(
        {"session_id": result.session_id, "saved": str(result.saved).lower()},
        as_json=output_json,
    )


def _parse_role_model_pairs(pairs: list[str], flag: str) -> dict[AgentRole, str]:
    result: dict[AgentRole, str] = {}
    for pair in pairs:
        if "=" not in pair:
            raise typer.BadParameter(f"{flag} must be ROLE=MODEL, got: {pair!r}")
        role_str, _, model_name = pair.partition("=")
        try:
            role = AgentRole(role_str)
        except ValueError:
            valid = ", ".join(r.value for r in AgentRole)
            raise typer.BadParameter(f"Unknown role {role_str!r}. Valid roles: {valid}")
        result[role] = model_name
    return result


def _parse_role_overrides(
    model_pairs: list[str],
    deep_model_pairs: list[str],
) -> dict[AgentRole, RoleOverride] | None:
    defaults = _parse_role_model_pairs(model_pairs, "--model")
    deeps = _parse_role_model_pairs(deep_model_pairs, "--deep-model")
    all_roles = set(defaults) | set(deeps)
    if not all_roles:
        return None
    return {
        role: RoleOverride(
            default_model=defaults.get(role),
            deep_model=deeps.get(role),
        )
        for role in all_roles
    }
