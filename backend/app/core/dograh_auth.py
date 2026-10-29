"""API key check for Dograh-facing routes (pre-call hook, tools)."""

import secrets
from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import get_settings
from app.core.errors import AppError


def get_dograh_api_key() -> str:
    key = get_settings().dograh_api_key
    if not key:
        raise AppError(500, "dograh_not_configured", "Dograh API key is not configured")
    return key


_bearer = HTTPBearer(auto_error=False)


async def require_dograh_key(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    expected: Annotated[str, Depends(get_dograh_api_key)],
) -> None:
    if credentials is None or not secrets.compare_digest(
        credentials.credentials.encode(), expected.encode()
    ):
        raise AppError(401, "unauthorized", "Missing or invalid API key")
