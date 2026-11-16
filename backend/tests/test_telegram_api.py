import re
from datetime import UTC, datetime, timedelta

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.web.telegram import get_bot_username
from app.core.config import get_settings
from app.main import app
from app.models import TelegramLink, User
from app.schemas.clerk import ClerkUserData
from app.services.identity import users
from app.services.identity.call_sessions import hash_token
from app.services.notification import telegram_links
from tests.conftest import TEST_BOT_USERNAME, HeadersFactory

LINK_PREFIX = f"https://t.me/{TEST_BOT_USERNAME}?start="
NOT_CONNECTED = {"enabled": True, "connected": False, "linked_at": None}


async def new_link(client: AsyncClient, headers: dict[str, str]) -> str:
    """Ask for a connect link and return its token."""
    response = await client.post("/api/telegram/link", headers=headers)
    assert response.status_code == 200
    return response.json()["url"].removeprefix(LINK_PREFIX)


async def user_by_clerk_id(session: AsyncSession, clerk_user_id: str) -> User:
    user = await session.scalar(select(User).where(User.clerk_user_id == clerk_user_id))
    assert user is not None
    return user


async def test_status_before_connecting(client: AsyncClient, auth_headers: HeadersFactory) -> None:
    response = await client.get("/api/telegram", headers=auth_headers("user_hoa"))

    assert response.status_code == 200
    assert response.json() == NOT_CONNECTED


async def test_connect_link_is_a_deep_link_with_a_hashed_one_time_token(
    client: AsyncClient, session: AsyncSession, auth_headers: HeadersFactory
) -> None:
    response = await client.post("/api/telegram/link", headers=auth_headers("user_hoa"))

    body = response.json()
    assert body["url"].startswith(LINK_PREFIX)
    token = body["url"].removeprefix(LINK_PREFIX)
    # Telegram start parameters: up to 64 of A-Z, a-z, 0-9, _ and -.
    assert re.fullmatch(r"[A-Za-z0-9_-]{43}", token)
    expires_at = datetime.fromisoformat(body["expires_at"])
    ttl = timedelta(minutes=get_settings().telegram_link_ttl_minutes)
    assert abs(expires_at - (datetime.now(UTC) + ttl)) < timedelta(minutes=1)

    link = await session.scalar(select(TelegramLink))
    assert link is not None and link.chat_id is None
    assert link.link_token_hash == hash_token(token)
    # Asking for a link doesn't connect anything yet.
    status = await client.get("/api/telegram", headers=auth_headers("user_hoa"))
    assert status.json() == NOT_CONNECTED


async def test_connected_once_the_bot_gets_the_token(
    client: AsyncClient, session: AsyncSession, auth_headers: HeadersFactory
) -> None:
    token = await new_link(client, auth_headers("user_hoa"))
    await telegram_links.redeem(session, token, chat_id=42)

    body = (await client.get("/api/telegram", headers=auth_headers("user_hoa"))).json()

    assert body["enabled"] is True and body["connected"] is True
    assert body["linked_at"] is not None


async def test_a_new_link_replaces_the_unused_one(
    client: AsyncClient, session: AsyncSession, auth_headers: HeadersFactory
) -> None:
    first = await new_link(client, auth_headers("user_hoa"))
    second = await new_link(client, auth_headers("user_hoa"))

    assert await telegram_links.redeem(session, first, chat_id=42) is None
    hoa = await user_by_clerk_id(session, "user_hoa")
    assert await telegram_links.redeem(session, second, chat_id=42) == hoa.id


async def test_a_new_link_keeps_the_connected_chat_until_it_is_used(
    client: AsyncClient, session: AsyncSession, auth_headers: HeadersFactory
) -> None:
    await telegram_links.redeem(session, await new_link(client, auth_headers("user_hoa")), 42)

    await new_link(client, auth_headers("user_hoa"))

    status = await client.get("/api/telegram", headers=auth_headers("user_hoa"))
    assert status.json()["connected"] is True


async def test_disconnect_stops_alerts_and_drops_the_unused_link(
    client: AsyncClient, session: AsyncSession, auth_headers: HeadersFactory
) -> None:
    await telegram_links.redeem(session, await new_link(client, auth_headers("user_hoa")), 42)
    unused = await new_link(client, auth_headers("user_hoa"))

    response = await client.delete("/api/telegram", headers=auth_headers("user_hoa"))

    assert response.status_code == 200
    assert response.json() == NOT_CONNECTED
    assert await session.scalar(select(TelegramLink)) is None
    assert await telegram_links.redeem(session, unused, chat_id=42) is None
    # Disconnecting again is fine.
    again = await client.delete("/api/telegram", headers=auth_headers("user_hoa"))
    assert again.status_code == 200


async def test_each_user_has_their_own_link(
    client: AsyncClient, session: AsyncSession, auth_headers: HeadersFactory
) -> None:
    await telegram_links.redeem(session, await new_link(client, auth_headers("user_hoa")), 42)

    other = await client.get("/api/telegram", headers=auth_headers("user_nam"))
    await client.delete("/api/telegram", headers=auth_headers("user_nam"))

    assert other.json() == NOT_CONNECTED
    hoa = await client.get("/api/telegram", headers=auth_headers("user_hoa"))
    assert hoa.json()["connected"] is True


async def test_deleting_a_user_removes_their_link(
    client: AsyncClient, session: AsyncSession, auth_headers: HeadersFactory
) -> None:
    await telegram_links.redeem(session, await new_link(client, auth_headers("user_hoa")), 42)

    await session.delete(await user_by_clerk_id(session, "user_hoa"))
    await session.flush()

    assert await session.scalar(select(TelegramLink)) is None


async def test_telegram_not_set_up(client: AsyncClient, auth_headers: HeadersFactory) -> None:
    app.dependency_overrides[get_bot_username] = lambda: None

    status = await client.get("/api/telegram", headers=auth_headers("user_hoa"))
    link = await client.post("/api/telegram/link", headers=auth_headers("user_hoa"))

    assert status.json() == {"enabled": False, "connected": False, "linked_at": None}
    assert link.status_code == 500
    assert link.json()["error"]["code"] == "telegram_not_configured"


async def test_family_members_only(
    client: AsyncClient, session: AsyncSession, auth_headers: HeadersFactory
) -> None:
    await users.upsert_from_clerk(
        session, ClerkUserData(id="user_admin", public_metadata={"role": "admin"})
    )

    for method, path in [
        ("GET", "/api/telegram"),
        ("POST", "/api/telegram/link"),
        ("DELETE", "/api/telegram"),
    ]:
        anonymous = await client.request(method, path)
        admin = await client.request(method, path, headers=auth_headers("user_admin"))
        assert anonymous.status_code == 401
        assert admin.status_code == 403
