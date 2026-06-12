"""Project-wide environment target enum and URL resolver."""

from __future__ import annotations

from enum import Enum

from sqlalchemy.engine import make_url

from macro_foundry.config import settings


class EnvTarget(str, Enum):
    """Named database environments accepted by all macrodb CLI commands.

    prod is deliberately absent: the CLI never targets production.
    Promotion is a separate outer workflow (see docs/environments.md).
    """

    DEV = "dev"
    TEST = "test"
    STAGING = "staging"


def app_url_for_target(target: EnvTarget) -> str:
    """Resolve the app-role database URL for an environment target."""

    if target is EnvTarget.TEST:
        return settings.db.test_url
    if target is EnvTarget.STAGING:
        if settings.db.staging_url is None:
            raise ValueError("MACRODB_STAGING_URL is required for --target staging")
        return settings.db.staging_url
    return settings.db.app_url


def owner_url_for_target(target: EnvTarget) -> str:
    """Resolve the owner-role database URL for an environment target.

    Reuses MACRODB_OWNER_URL's host/credentials but substitutes the
    database name of the selected target. This mirrors the pattern in
    tests/conftest.py so migrations can land on whichever physical
    database the user is operating against.
    """

    owner = make_url(settings.db.owner_url)
    if target is EnvTarget.DEV:
        return owner.render_as_string(hide_password=False)
    target_db = make_url(app_url_for_target(target)).database
    if target_db is None:
        raise ValueError(f"Cannot resolve database name for target {target.value!r}")
    return owner.set(database=target_db).render_as_string(hide_password=False)


__all__ = ["EnvTarget", "app_url_for_target", "owner_url_for_target"]
