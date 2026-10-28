"""Clerk JWT verification and current-user dependencies for web routes."""

from collections.abc import Awaitable, Callable, Sequence
from functools import lru_cache
from typing import Annotated, Any, Protocol

import jwt
from fastapi import Depends
from fastapi.concurrency import run_in_threadpool
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import get_db
from app.core.errors import AppError
from app.models import User, UserRole
from app.services.identity import users


class SigningKeyResolver(Protocol):
    def get_signing_key_from_jwt(self, token: str) -> jwt.PyJWK: ...


class ClerkJWTVerifier:
    def __init__(
        self,
        issuer: str,
        authorized_parties: Sequence[str],
        key_resolver: SigningKeyResolver | None = None,
    ) -> None:
        self._issuer = issuer
        self._authorized_parties = set(authorized_parties)
        self._key_resolver = key_resolver or jwt.PyJWKClient(
            f"{issuer.rstrip('/')}/.well-known/jwks.json", cache_keys=True
        )

    def verify(self, token: str) -> dict[str, Any]:
        """Claims of a valid Clerk session token; raises 401 otherwise. May fetch JWKS."""
        try:
            key = self._key_resolver.get_signing_key_from_jwt(token)
            claims: dict[str, Any] = jwt.decode(
                token,
                key.key,
                algorithms=["RS256"],
                issuer=self._issuer,
                leeway=5,
                options={"require": ["exp", "nbf", "iat", "iss", "sub"]},
            )
        except jwt.PyJWTError as exc:
            raise AppError(401, "unauthorized", "Invalid or expired token") from exc

        azp = claims.get("azp")
        if azp is not None and azp not in self._authorized_parties:
            raise AppError(401, "unauthorized", "Token issued for an unknown origin")
        return claims


@lru_cache
def _default_verifier(issuer: str, authorized_parties: tuple[str, ...]) -> ClerkJWTVerifier:
    return ClerkJWTVerifier(issuer, authorized_parties)


def get_verifier() -> ClerkJWTVerifier:
    settings = get_settings()
    if not settings.clerk_issuer:
        raise AppError(500, "auth_not_configured", "Authentication is not configured")
    return _default_verifier(settings.clerk_issuer, tuple(settings.clerk_authorized_parties))


_bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    verifier: Annotated[ClerkJWTVerifier, Depends(get_verifier)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    if credentials is None:
        raise AppError(401, "unauthorized", "Missing bearer token")
    # JWKS fetch is blocking I/O (keys are cached after the first call).
    claims = await run_in_threadpool(verifier.verify, credentials.credentials)
    user = await users.get_or_create(db, claims["sub"])
    await db.commit()
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_role(*roles: UserRole) -> Callable[[User], Awaitable[User]]:
    async def dependency(user: CurrentUser) -> User:
        if user.role not in roles:
            raise AppError(403, "forbidden", "Insufficient permissions")
        return user

    return dependency
