from datetime import UTC, datetime, timedelta

from httpx import AsyncClient, Response
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import CallSession, Elder, ElderStatus
from tests.conftest import DOGRAH_HEADERS, add_elder, start_call


async def confirm(
    client: AsyncClient, token: str, headers: dict[str, str] = DOGRAH_HEADERS
) -> Response:
    return await client.post(
        "/tools/confirm-activation", json={"session_token": token}, headers=headers
    )


async def test_pending_elder_is_activated_with_consent_time(
    client: AsyncClient, session: AsyncSession
) -> None:
    elder = await add_elder(session, status=ElderStatus.PENDING_VERIFICATION)
    token = await start_call(client)

    response = await confirm(client, token)

    assert response.status_code == 200
    assert response.json() == {
        "status": "activated",
        "message": "Đã kích hoạt dịch vụ cho số điện thoại này.",
        "preferred_name": "bà Lan",
    }
    await session.refresh(elder)
    assert elder.status is ElderStatus.ACTIVE
    assert elder.consent_at is not None
    assert abs(elder.consent_at - datetime.now(UTC)) < timedelta(minutes=1)


async def test_confirming_again_keeps_the_first_consent_time(
    client: AsyncClient, session: AsyncSession
) -> None:
    elder = await add_elder(session, status=ElderStatus.PENDING_VERIFICATION, preferred_name=None)
    token = await start_call(client)
    await confirm(client, token)
    await session.refresh(elder)
    consent_at = elder.consent_at

    response = await confirm(client, token)

    assert response.status_code == 200
    assert response.json()["status"] == "already_active"
    assert response.json()["preferred_name"] == "Nguyễn Thị Lan"
    await session.refresh(elder)
    assert elder.consent_at == consent_at


async def test_unknown_caller_cannot_activate(client: AsyncClient, session: AsyncSession) -> None:
    await add_elder(session, status=ElderStatus.PENDING_VERIFICATION)
    token = await start_call(client, from_number="0987654321")

    response = await confirm(client, token)

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_registered"


async def test_elder_blocked_during_the_call_cannot_activate(
    client: AsyncClient, session: AsyncSession
) -> None:
    elder = await add_elder(session, status=ElderStatus.PENDING_VERIFICATION)
    token = await start_call(client)
    await session.execute(
        update(Elder).where(Elder.id == elder.id).values(status=ElderStatus.BLOCKED)
    )

    response = await confirm(client, token)

    assert response.status_code == 404
    await session.refresh(elder)
    assert elder.consent_at is None


async def test_expired_or_unknown_token_is_rejected(
    client: AsyncClient, session: AsyncSession
) -> None:
    await add_elder(session, status=ElderStatus.PENDING_VERIFICATION)
    token = await start_call(client)
    await session.execute(
        update(CallSession).values(expires_at=datetime.now(UTC) - timedelta(seconds=1))
    )

    for candidate in (token, "made-up-token"):
        response = await confirm(client, candidate)
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "invalid_session"


async def test_missing_session_token_is_a_validation_error(client: AsyncClient) -> None:
    response = await client.post("/tools/confirm-activation", json={}, headers=DOGRAH_HEADERS)

    assert response.status_code == 422


async def test_tool_requires_the_api_key(client: AsyncClient, session: AsyncSession) -> None:
    elder = await add_elder(session, status=ElderStatus.PENDING_VERIFICATION)
    token = await start_call(client)

    response = await confirm(client, token, headers={})

    assert response.status_code == 401
    await session.refresh(elder)
    assert elder.status is ElderStatus.PENDING_VERIFICATION
