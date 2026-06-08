"""Basic auth backend for SQLAdmin."""

from __future__ import annotations

import secrets

from sqladmin.authentication import AuthenticationBackend
from starlette.requests import Request
from starlette.responses import Response

from macro_foundry.config import settings

_SESSION_KEY = "macrodb_admin_authenticated"


class BasicAuthBackend(AuthenticationBackend):
    """Authenticate SQLAdmin with one configured username/password pair."""

    def __init__(self) -> None:
        super().__init__(secret_key=settings.admin.session_secret.get_secret_value())

    async def login(self, request: Request) -> bool:
        form = await request.form()
        expected_username = settings.admin.username
        expected_password = settings.admin.password.get_secret_value()
        provided_username = str(form.get("username") or "")
        provided_password = str(form.get("password") or "")

        if not secrets.compare_digest(provided_username, expected_username):
            return False
        if not secrets.compare_digest(provided_password, expected_password):
            return False

        request.session.update({_SESSION_KEY: True, "admin_username": provided_username})
        return True

    async def logout(self, request: Request) -> Response | bool:
        request.session.clear()
        return True

    async def authenticate(self, request: Request) -> bool:
        return bool(request.session.get(_SESSION_KEY))


__all__ = ["BasicAuthBackend"]
