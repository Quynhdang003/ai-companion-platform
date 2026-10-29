import asyncio
import base64
import uuid
from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import asyncpg
import jwt
import pytest
from alembic.config import Config
from cryptography.hazmat.primitives.asymmetric import rsa
from httpx import ASGITransport, AsyncClient
from jwt.algorithms import RSAAlgorithm
from sqlalchemy import make_url
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool
from svix.webhooks import Webhook

from alembic import command
from app.api.webhooks.clerk import get_clerk_webhook
from app.core.auth import ClerkJWTVerifier, get_verifier
from app.core.config import get_settings
from app.core.db import get_db
from app.main import app

BACKEND_DIR = Path(__file__).resolve().parents[1]

TEST_ISSUER = "https://test.clerk.example"
TEST_AZP = "http://localhost:3000"
WEBHOOK_SECRET = "whsec_" + base64.b64encode(b"test-webhook-secret-0123").decode()

TokenFactory = Callable[..., str]
HeadersFactory = Callable[[str], dict[str, str]]


def alembic_config(db_url: str) -> Config:
    config = Config(BACKEND_DIR / "alembic.ini")
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    config.set_main_option("sqlalchemy.url", db_url.replace("%", "%%"))
    return config


async def _recreate_database(db_url: str) -> None:
    url = make_url(db_url)
    # Guard against pointing the suite at the dev database: it gets dropped.
    if url.database is None or not url.database.endswith("_test"):
        raise RuntimeError(f"Refusing to recreate non-test database {url.database!r}")
    admin_url = url.set(drivername="postgresql", database="postgres")
    conn = await asyncpg.connect(admin_url.render_as_string(hide_password=False))
    try:
        await conn.execute(f'DROP DATABASE IF EXISTS "{url.database}" WITH (FORCE)')
        await conn.execute(f'CREATE DATABASE "{url.database}"')
    finally:
        await conn.close()


@pytest.fixture(scope="session")
def migrated_db() -> str:
    """Fresh test database at Alembic head; returns its URL."""
    db_url = get_settings().test_database_url
    asyncio.run(_recreate_database(db_url))
    command.upgrade(alembic_config(db_url), "head")
    return db_url


@pytest.fixture
async def session(migrated_db: str) -> AsyncIterator[AsyncSession]:
    """Session inside an outer transaction that is rolled back after each test.

    `commit()` in app code only releases a savepoint, so tests stay isolated.
    """
    engine = create_async_engine(migrated_db, poolclass=NullPool)
    async with engine.connect() as conn:
        trans = await conn.begin()
        async with AsyncSession(
            bind=conn, join_transaction_mode="create_savepoint", expire_on_commit=False
        ) as s:
            yield s
        await trans.rollback()
    await engine.dispose()


@pytest.fixture(scope="session")
def rsa_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


class StaticKeyResolver:
    def __init__(self, key: rsa.RSAPrivateKey) -> None:
        self._jwk = jwt.PyJWK.from_json(RSAAlgorithm.to_jwk(key.public_key()))

    def get_signing_key_from_jwt(self, token: str) -> jwt.PyJWK:
        return self._jwk


@pytest.fixture
def make_token(rsa_key: rsa.RSAPrivateKey) -> TokenFactory:
    """Signs a Clerk-like session token; pass `claim=None` to drop a claim."""

    def factory(key: rsa.RSAPrivateKey | None = None, **overrides: Any) -> str:
        now = datetime.now(UTC)
        claims: dict[str, Any] = {
            "sub": "user_test",
            "iss": TEST_ISSUER,
            "azp": TEST_AZP,
            "iat": now,
            "nbf": now,
            "exp": now + timedelta(minutes=1),
        }
        claims.update(overrides)
        claims = {k: v for k, v in claims.items() if v is not None}
        return jwt.encode(claims, key or rsa_key, algorithm="RS256", headers={"kid": "test"})

    return factory


@pytest.fixture
def auth_headers(make_token: TokenFactory) -> HeadersFactory:
    """Bearer headers for a Clerk user id; the user is created as `family` on first request."""
    return lambda sub: {"Authorization": f"Bearer {make_token(sub=sub)}"}


@pytest.fixture
async def client(session: AsyncSession, rsa_key: rsa.RSAPrivateKey) -> AsyncIterator[AsyncClient]:
    verifier = ClerkJWTVerifier(TEST_ISSUER, [TEST_AZP], StaticKeyResolver(rsa_key))
    app.dependency_overrides[get_db] = lambda: session
    app.dependency_overrides[get_verifier] = lambda: verifier
    app.dependency_overrides[get_clerk_webhook] = lambda: Webhook(WEBHOOK_SECRET)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            yield c
    finally:
        app.dependency_overrides.clear()


def svix_headers(body: str, secret: str = WEBHOOK_SECRET) -> dict[str, str]:
    msg_id = f"msg_{uuid.uuid4().hex}"
    timestamp = datetime.now(UTC)
    return {
        "content-type": "application/json",
        "svix-id": msg_id,
        "svix-timestamp": str(int(timestamp.timestamp())),
        "svix-signature": Webhook(secret).sign(msg_id, timestamp, body),
    }
