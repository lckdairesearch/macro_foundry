"""Onboarding target selection — re-exports EnvTarget from db.env_target."""

from __future__ import annotations

from macro_foundry.db.env_target import EnvTarget, database_url_for_env_target

OnboardingTarget = EnvTarget
database_url_for_onboarding_target = database_url_for_env_target

__all__ = [
    "OnboardingTarget",
    "database_url_for_onboarding_target",
]
