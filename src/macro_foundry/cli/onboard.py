"""`macrodb onboard` command."""

from __future__ import annotations

import asyncio
from typing import Annotated

import typer

from macro_foundry.agent.onboarding import OnboardingResult, OnboardingTarget, run_onboarding_session

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
) -> None:
    """Open the gated onboarding chat shell."""

    try:
        result: OnboardingResult = asyncio.run(
            run_onboarding_session(
                target=target,
                resume_session_id=resume_session_id,
            ),
        )
    except ValueError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc
    typer.echo(f"session_id={result.session_id} saved={str(result.saved).lower()}")
