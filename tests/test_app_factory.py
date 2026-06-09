"""Focused coverage for database-targeted app construction."""

from __future__ import annotations

from sqlalchemy.engine import make_url

from macro_foundry.backend.deps import get_session
from macro_foundry.backend.main import create_app
from macro_foundry.config import settings


def test_create_app_can_target_test_database() -> None:
    app = create_app(database_url=settings.db.test_url)

    assert get_session in app.dependency_overrides
    assert app.state.database_url == settings.db.test_url
    assert make_url(str(app.state.admin.engine.url)).database == make_url(settings.db.test_url).database
