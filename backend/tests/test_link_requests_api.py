import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ElderFamily, FamilyRole
from app.schemas.clerk import ClerkUserData
from app.services.identity import users
from tests.conftest import HeadersFactory

OWNER, REQUESTER, STRANGER = "user_owner", "user_req", "user_other"


@pytest.fixture
async def request_id(
    client: AsyncClient, session: AsyncSession, auth_headers: HeadersFactory
) -> str:
    """OWNER registered the elder; REQUESTER (synced from Clerk) asked to be linked."""
    await users.upsert_from_clerk(
        session,
        ClerkUserData(
            id=REQUESTER,
            first_name="Hoa",
            last_name="Nguyễn",
            email_addresses=[{"id": "e1", "email_address": "hoa@example.com"}],
            primary_email_address_id="e1",
        ),
    )
    body = {"full_name": "Nguyễn Thị Lan", "phone": "0912345678"}
    await client.post("/api/elders", json=body, headers=auth_headers(OWNER))
    response = await client.post("/api/elders", json=body, headers=auth_headers(REQUESTER))
    assert response.status_code == 202

    incoming = await client.get("/api/link-requests/incoming", headers=auth_headers(OWNER))
    return incoming.json()[0]["id"]


async def test_owner_sees_incoming_request_with_requester_identity(
    client: AsyncClient, auth_headers: HeadersFactory, request_id: str
) -> None:
    response = await client.get("/api/link-requests/incoming", headers=auth_headers(OWNER))

    assert response.status_code == 200
    [item] = response.json()
    assert item["id"] == request_id
    assert item["elder"]["full_name"] == "Nguyễn Thị Lan"
    assert item["requester"] == {"display_name": "Hoa Nguyễn", "email": "hoa@example.com"}


async def test_others_see_no_incoming_requests(
    client: AsyncClient, auth_headers: HeadersFactory, request_id: str
) -> None:
    for sub in (REQUESTER, STRANGER):
        response = await client.get("/api/link-requests/incoming", headers=auth_headers(sub))
        assert response.json() == []


async def test_outgoing_hides_elder_name_until_approved(
    client: AsyncClient, auth_headers: HeadersFactory, request_id: str
) -> None:
    pending = await client.get("/api/link-requests/outgoing", headers=auth_headers(REQUESTER))
    [item] = pending.json()
    assert (item["status"], item["elder_full_name"]) == ("pending", None)
    assert item["phone_e164"] == "+84912345678"

    await client.post(f"/api/link-requests/{request_id}/approve", headers=auth_headers(OWNER))

    approved = await client.get("/api/link-requests/outgoing", headers=auth_headers(REQUESTER))
    [item] = approved.json()
    assert (item["status"], item["elder_full_name"]) == ("approved", "Nguyễn Thị Lan")
    assert item["decided_at"] is not None


async def test_approve_links_requester_as_viewer(
    client: AsyncClient, auth_headers: HeadersFactory, request_id: str
) -> None:
    response = await client.post(
        f"/api/link-requests/{request_id}/approve", headers=auth_headers(OWNER)
    )

    assert response.status_code == 200
    assert response.json()["status"] == "approved"
    elders = await client.get("/api/elders", headers=auth_headers(REQUESTER))
    assert [(e["full_name"], e["my_role"]) for e in elders.json()] == [("Nguyễn Thị Lan", "viewer")]
    incoming = await client.get("/api/link-requests/incoming", headers=auth_headers(OWNER))
    assert incoming.json() == []


async def test_reject_creates_no_link(
    client: AsyncClient, session: AsyncSession, auth_headers: HeadersFactory, request_id: str
) -> None:
    response = await client.post(
        f"/api/link-requests/{request_id}/reject", headers=auth_headers(OWNER)
    )

    assert response.json()["status"] == "rejected"
    requester = await users.get_or_create(session, REQUESTER)
    link = await session.scalar(select(ElderFamily).where(ElderFamily.user_id == requester.id))
    assert link is None


async def test_rejected_requester_can_ask_again(
    client: AsyncClient, auth_headers: HeadersFactory, request_id: str
) -> None:
    await client.post(f"/api/link-requests/{request_id}/reject", headers=auth_headers(OWNER))
    body = {"full_name": "Nguyễn Thị Lan", "phone": "0912345678"}

    response = await client.post("/api/elders", json=body, headers=auth_headers(REQUESTER))

    assert response.status_code == 202
    incoming = await client.get("/api/link-requests/incoming", headers=auth_headers(OWNER))
    assert len(incoming.json()) == 1


async def test_deciding_twice_is_a_conflict(
    client: AsyncClient, auth_headers: HeadersFactory, request_id: str
) -> None:
    await client.post(f"/api/link-requests/{request_id}/approve", headers=auth_headers(OWNER))

    response = await client.post(
        f"/api/link-requests/{request_id}/reject", headers=auth_headers(OWNER)
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "already_decided"


@pytest.mark.parametrize("sub", [REQUESTER, STRANGER])
async def test_non_owner_cannot_decide(
    client: AsyncClient, auth_headers: HeadersFactory, request_id: str, sub: str
) -> None:
    response = await client.post(
        f"/api/link-requests/{request_id}/approve", headers=auth_headers(sub)
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


async def test_viewer_cannot_decide(
    client: AsyncClient, session: AsyncSession, auth_headers: HeadersFactory, request_id: str
) -> None:
    """Only the owner decides, even after other family members were linked as viewers."""
    elders = await client.get("/api/elders", headers=auth_headers(OWNER))
    viewer = await users.get_or_create(session, STRANGER)
    session.add(
        ElderFamily(elder_id=elders.json()[0]["id"], user_id=viewer.id, role=FamilyRole.VIEWER)
    )
    await session.flush()

    response = await client.post(
        f"/api/link-requests/{request_id}/approve", headers=auth_headers(STRANGER)
    )

    assert response.status_code == 404


async def test_unknown_request_is_not_found(
    client: AsyncClient, auth_headers: HeadersFactory
) -> None:
    response = await client.post(
        f"/api/link-requests/{uuid.uuid4()}/approve", headers=auth_headers(OWNER)
    )

    assert response.status_code == 404
