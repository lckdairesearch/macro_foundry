"""Onboarding target selection."""

from __future__ import annotations

from enum import Enum

from macro_foundry.config import settings


class OnboardingTarget(str, Enum):
    """Durable onboarding targets accepted by the agent CLI."""

    DEV = "dev"
    STAGING = "staging"


def database_url_for_onboarding_target(target: OnboardingTarget) -> str:
    """Resolve the app-role database URL for an onboarding target."""

    if target is OnboardingTarget.DEV:
        return settings.db.app_url
    if settings.db.staging_url is None:
        raise ValueError("MACRODB_STAGING_URL is required for --target staging")
    return settings.db.staging_url


__all__ = [
    "OnboardingTarget",
    "database_url_for_onboarding_target",
]
