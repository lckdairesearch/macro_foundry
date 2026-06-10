"""Project-wide environment target enum and URL resolver."""

from __future__ import annotations

from enum import Enum

from macro_foundry.config import settings


class EnvTarget(str, Enum):
    """Named database environments accepted by all macrodb CLI commands.

    prod is deliberately absent: the CLI never targets production.
    Promotion is a separate outer workflow (see docs/environments.md).
    """

    DEV = "dev"
    TEST = "test"
    STAGING = "staging"


def database_url_for_env_target(target: EnvTarget) -> str:
    """Resolve the app-role database URL for an environment target."""

    if target is EnvTarget.TEST:
        return settings.db.test_url
    if target is EnvTarget.STAGING:
        if settings.db.staging_url is None:
            raise ValueError("MACRODB_STAGING_URL is required for --target staging")
        return settings.db.staging_url
    return settings.db.app_url


__all__ = ["EnvTarget", "database_url_for_env_target"]
