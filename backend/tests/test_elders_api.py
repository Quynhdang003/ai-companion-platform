import uuid
from typing import Any

import pytest
from httpx import AsyncClient, Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Elder, ElderFamily, ElderLinkRequest, FamilyRole, LinkRequestStatus
from app.schemas.clerk import ClerkUserData
from app.services.identity import users
from tests.conftest import HeadersFactory

PHONE = "+84912345678"


async def register(
    client: AsyncClient, headers: dict[str, str], phone: str = "0912 345 678", **extra: Any
) -> Response:
    body = {"full_name": "Nguyễn Thị Lan", "phone": phone, **extra}
    return await client.post("/api/elders", json=body, headers=headers)


async def count_requests(session: AsyncSession) -> int:
    return await session.scalar(select(func.count()).select_from(ElderLinkRequest))


async def test_new_number_creates_pending_elder_owned_by_user(
    client: AsyncClient, session: AsyncSession, auth_headers: HeadersFactory
) -> None:
    response = await register(client, auth_headers("user_a"), preferred_name="  bà Lan ")

    assert response.status_code == 201
    body = response.json()
    assert body["result"] == "created"
    assert body["elder"]["phone_e164"] == PHONE
    assert body["elder"]["preferred_name"] == "bà Lan"
    assert body["elder"]["status"] == "PENDING_VERIFICATION"
    assert body["elder"]["my_role"] == "owner"
    link = await session.scalar(
        select(ElderFamily).where(ElderFamily.elder_id == uuid.UUID(body["elder"]["id"]))
    )
    assert link is not None and link.role is FamilyRole.OWNER


async def test_blank_preferred_name_is_stored_as_null(
    client: AsyncClient, auth_headers: HeadersFactory
) -> None:
    response = await register(client, auth_headers("user_a"), preferred_name="   ")

    assert response.json()["elder"]["preferred_name"] is None


async def test_taken_number_sends_one_link_request_without_leaking_elder(
    client: AsyncClient, session: AsyncSession, auth_headers: HeadersFactory
) -> None:
    await register(client, auth_headers("user_a"))

    first = await register(client, auth_headers("user_b"), phone="+84 912 345 678")
    again = await register(client, auth_headers("user_b"))

    assert first.status_code == again.status_code == 202
    assert first.json() == {"result": "link_requested", "elder": None}
    request = await session.scalar(select(ElderLinkRequest))
    assert request is not None and request.status is LinkRequestStatus.PENDING
    assert await count_requests(session) == 1
    assert await session.scalar(select(func.count()).select_from(Elder)) == 1


@pytest.mark.parametrize("role", [FamilyRole.OWNER, FamilyRole.VIEWER])
async def test_already_linked_user_gets_conflict(
    client: AsyncClient, session: AsyncSession, auth_headers: HeadersFactory, role: FamilyRole
) -> None:
    created = await register(client, auth_headers("user_a"))
    if role is FamilyRole.VIEWER:
        viewer = await users.get_or_create(session, "user_v")
        session.add(
            ElderFamily(elder_id=created.json()["elder"]["id"], user_id=viewer.id, role=role)
        )
        await session.flush()
    sub = "user_a" if role is FamilyRole.OWNER else "user_v"

    response = await register(client, auth_headers(sub))

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "already_linked"
    assert await count_requests(session) == 0


async def test_invalid_phone_is_rejected(client: AsyncClient, auth_headers: HeadersFactory) -> None:
    response = await register(client, auth_headers("user_a"), phone="1900 1234")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_phone"


@pytest.mark.parametrize("body", [{"full_name": "  ", "phone": PHONE}, {"phone": PHONE}])
async def test_missing_name_is_a_validation_error(
    client: AsyncClient, auth_headers: HeadersFactory, body: dict[str, str]
) -> None:
    response = await client.post("/api/elders", json=body, headers=auth_headers("user_a"))

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


async def test_admin_cannot_register(
    client: AsyncClient, session: AsyncSession, auth_headers: HeadersFactory
) -> None:
    await users.upsert_from_clerk(
        session, ClerkUserData(id="user_admin", public_metadata={"role": "admin"})
    )

    response = await register(client, auth_headers("user_admin"))

    assert response.status_code == 403


async def test_requires_authentication(client: AsyncClient) -> None:
    assert (await register(client, {})).status_code == 401
    assert (await client.get("/api/elders")).status_code == 401


async def test_list_returns_only_own_elders(
    client: AsyncClient, auth_headers: HeadersFactory
) -> None:
    await register(client, auth_headers("user_a"))
    await register(client, auth_headers("user_b"), phone="0987654321")

    response = await client.get("/api/elders", headers=auth_headers("user_a"))

    assert response.status_code == 200
    assert [e["phone_e164"] for e in response.json()] == [PHONE]
    assert response.json()[0]["my_role"] == "owner"
