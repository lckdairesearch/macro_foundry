"""Shared FastAPI dependencies for the backend."""

from __future__ import annotations

import secrets

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from macro_foundry.config import settings
from macro_foundry.db.session import get_session

_bearer_scheme = HTTPBearer(auto_error=False)


async def verify_token(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> None:
    """Reject requests that do not provide the configured bearer token."""

    expected_token = settings.api.bearer_token.get_secret_value()
    provided_token = credentials.credentials if credentials is not None else None
    if provided_token is None or not secrets.compare_digest(provided_token, expected_token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )


__all__ = ["get_session", "verify_token"]
