import json
from typing import Any

from httpx import AsyncClient, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Elder, ElderFamily, FamilyRole, User, UserRole
from app.services.identity import users
from tests.conftest import WEBHOOK_SECRET, svix_headers


async def post_event(client: AsyncClient, event_type: str, data: dict[str, Any]) -> Response:
    body = json.dumps({"type": event_type, "object": "event", "data": data})
    return await client.post("/webhooks/clerk", content=body, headers=svix_headers(body))


async def get_user(session: AsyncSession, clerk_user_id: str) -> User | None:
    return await session.scalar(select(User).where(User.clerk_user_id == clerk_user_id))


async def test_bad_signature_is_rejected(client: AsyncClient, session: AsyncSession) -> None:
    body = json.dumps({"type": "user.created", "data": {"id": "user_x"}})
    headers = svix_headers(body, secret=WEBHOOK_SECRET[:-4] + "AAA=")

    response = await client.post("/webhooks/clerk", content=body, headers=headers)

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_signature"
    assert await get_user(session, "user_x") is None


async def test_user_created_with_admin_role(client: AsyncClient, session: AsyncSession) -> None:
    response = await post_event(
        client, "user.created", {"id": "user_a", "public_metadata": {"role": "admin"}}
    )

    assert response.status_code == 200
    assert response.json() == {"received": True}
    user = await get_user(session, "user_a")
    assert user is not None and user.role is UserRole.ADMIN


async def test_user_updated_changes_role_and_falls_back_to_family(
    client: AsyncClient, session: AsyncSession
) -> None:
    await post_event(client, "user.created", {"id": "user_b", "public_metadata": {}})
    await post_event(client, "user.updated", {"id": "user_b", "public_metadata": {"role": "admin"}})
    user = await get_user(session, "user_b")
    assert user is not None and user.role is UserRole.ADMIN

    await post_event(client, "user.updated", {"id": "user_b", "public_metadata": {"role": "root"}})

    user = await get_user(session, "user_b")
    assert user is not None and user.role is UserRole.FAMILY


async def test_user_created_stores_name_and_primary_email(
    client: AsyncClient, session: AsyncSession
) -> None:
    await post_event(
        client,
        "user.created",
        {
            "id": "user_n",
            "first_name": "Hoa",
            "last_name": "Nguyễn",
            "email_addresses": [{"id": "idn_1", "email_address": "hoa@example.com"}],
            "primary_email_address_id": "idn_1",
        },
    )

    user = await get_user(session, "user_n")
    assert user is not None
    assert (user.display_name, user.email) == ("Hoa Nguyễn", "hoa@example.com")


async def test_webhook_after_lazy_create_updates_same_row(
    client: AsyncClient, session: AsyncSession
) -> None:
    lazy = await users.get_or_create(session, "user_c")

    await post_event(client, "user.created", {"id": "user_c", "public_metadata": {"role": "admin"}})

    user = await get_user(session, "user_c")
    assert user is not None
    assert user.id == lazy.id
    assert user.role is UserRole.ADMIN


async def test_user_deleted_removes_links_but_keeps_elder(
    client: AsyncClient, session: AsyncSession
) -> None:
    user = await users.get_or_create(session, "user_d")
    elder = Elder(phone_e164="+84912345678", full_name="A")
    session.add(elder)
    await session.flush()
    session.add(ElderFamily(elder_id=elder.id, user_id=user.id, role=FamilyRole.OWNER))
    await session.flush()

    response = await post_event(client, "user.deleted", {"id": "user_d", "deleted": True})

    assert response.status_code == 200
    assert await get_user(session, "user_d") is None
    assert await session.scalar(select(ElderFamily).where(ElderFamily.user_id == user.id)) is None
    assert await session.scalar(select(Elder).where(Elder.id == elder.id)) is not None


async def test_other_events_are_ignored(client: AsyncClient, session: AsyncSession) -> None:
    response = await post_event(client, "session.created", {"id": "sess_1", "user_id": "user_e"})

    assert response.status_code == 200
    assert await get_user(session, "user_e") is None


async def test_user_event_without_id_is_invalid(client: AsyncClient) -> None:
    response = await post_event(client, "user.created", {"public_metadata": {}})

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_payload"
