from datetime import UTC, datetime, timedelta

import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import require_role
from app.core.errors import AppError
from app.models import User, UserRole
from tests.conftest import TokenFactory


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def test_missing_token_is_unauthorized(client: AsyncClient) -> None:
    response = await client.get("/api/me")

    assert response.status_code == 401
    assert response.json() == {"error": {"code": "unauthorized", "message": "Missing bearer token"}}


@pytest.mark.parametrize(
    "overrides",
    [
        {"iss": "https://evil.example"},
        {"azp": "https://evil.example"},
        {"exp": datetime.now(UTC) - timedelta(minutes=1)},
        {"sub": None},
    ],
    ids=["wrong-issuer", "unknown-azp", "expired", "no-sub"],
)
async def test_invalid_claims_are_unauthorized(
    client: AsyncClient, make_token: TokenFactory, overrides: dict[str, object]
) -> None:
    response = await client.get("/api/me", headers=bearer(make_token(**overrides)))

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


async def test_malformed_token_is_unauthorized(client: AsyncClient) -> None:
    response = await client.get("/api/me", headers=bearer("not-a-jwt"))

    assert response.status_code == 401


async def test_token_signed_by_other_key_is_unauthorized(
    client: AsyncClient, make_token: TokenFactory
) -> None:
    other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    response = await client.get("/api/me", headers=bearer(make_token(key=other_key)))

    assert response.status_code == 401


async def test_first_request_creates_family_user_once(
    client: AsyncClient, session: AsyncSession, make_token: TokenFactory
) -> None:
    token = make_token(sub="user_new")

    first = await client.get("/api/me", headers=bearer(token))
    second = await client.get("/api/me", headers=bearer(token))

    assert first.status_code == 200
    assert first.json()["clerk_user_id"] == "user_new"
    assert first.json()["role"] == "family"
    assert second.json()["id"] == first.json()["id"]
    count = await session.scalar(
        select(func.count()).select_from(User).where(User.clerk_user_id == "user_new")
    )
    assert count == 1


async def test_require_role_rejects_other_roles() -> None:
    admin_only = require_role(UserRole.ADMIN)

    with pytest.raises(AppError) as exc_info:
        await admin_only(User(clerk_user_id="u", role=UserRole.FAMILY))
    assert exc_info.value.status_code == 403

    admin = User(clerk_user_id="a", role=UserRole.ADMIN)
    assert await admin_only(admin) is admin
