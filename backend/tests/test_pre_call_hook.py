from typing import Any

import pytest
from httpx import AsyncClient, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.dograh_auth import get_dograh_api_key
from app.main import app
from app.models import CallSession, ElderStatus
from app.services.identity import call_sessions
from tests.conftest import DOGRAH_HEADERS, add_elder

PHONE = "+84912345678"


async def pre_call(
    client: AsyncClient,
    from_number: str | None = "0912 345 678",
    *,
    run_id: Any = 42,
    headers: dict[str, str] = DOGRAH_HEADERS,
) -> Response:
    """Request shaped like Dograh's pre-call data fetch."""
    body = {
        "event": "call_inbound",
        "call_inbound": {
            "agent_id": 3,
            "workflow_run_id": run_id,
            "from_number": from_number,
            "to_number": "+842412345678",
        },
    }
    return await client.post("/hooks/pre-call", json=body, headers=headers)


def context_of(response: Response) -> dict[str, Any]:
    """`initial_context` without the (random) session token."""
    assert response.status_code == 200
    context = response.json()["initial_context"]
    assert context.pop("session_token")
    return context


async def test_active_caller_gets_names_and_a_linked_session(
    client: AsyncClient, session: AsyncSession
) -> None:
    elder = await add_elder(session, status=ElderStatus.ACTIVE)

    response = await pre_call(client)

    token = response.json()["initial_context"]["session_token"]
    assert context_of(response) == {
        "caller_status": "active",
        "is_registered": True,
        "full_name": "Nguyễn Thị Lan",
        "preferred_name": "bà Lan",
    }
    call = await call_sessions.resolve(session, token)
    assert call.elder_id == elder.id
    assert call.from_number == PHONE
    assert call.workflow_run_id == "42"


@pytest.mark.parametrize("from_number", ["+84912345678", "84912345678", "0912.345.678"])
async def test_caller_is_recognised_in_any_notation(
    client: AsyncClient, session: AsyncSession, from_number: str
) -> None:
    await add_elder(session, status=ElderStatus.ACTIVE)

    context = context_of(await pre_call(client, from_number))

    assert context["caller_status"] == "active"


async def test_active_caller_without_preferred_name_is_greeted_by_full_name(
    client: AsyncClient, session: AsyncSession
) -> None:
    await add_elder(session, status=ElderStatus.ACTIVE, preferred_name=None)

    context = context_of(await pre_call(client))

    assert context["preferred_name"] == "Nguyễn Thị Lan"


async def test_pending_caller_only_learns_who_registered(
    client: AsyncClient, session: AsyncSession
) -> None:
    await add_elder(session, status=ElderStatus.PENDING_VERIFICATION, owner_name="Hoa")

    context = context_of(await pre_call(client))

    assert context == {
        "caller_status": "pending_consent",
        "is_registered": True,
        "registered_by": "Hoa",
    }


async def test_pending_caller_with_unsynced_owner_name_omits_registered_by(
    client: AsyncClient, session: AsyncSession
) -> None:
    await add_elder(session, status=ElderStatus.PENDING_VERIFICATION, owner_name=None)

    context = context_of(await pre_call(client))

    assert context == {"caller_status": "pending_consent", "is_registered": True}


# Unregistered number, web call without caller_number (empty or missing), garbage.
@pytest.mark.parametrize("from_number", ["0987654321", "", None, "anonymous"])
async def test_unknown_caller_gets_a_session_without_personal_data(
    client: AsyncClient, session: AsyncSession, from_number: str | None
) -> None:
    await add_elder(session, status=ElderStatus.ACTIVE)

    context = context_of(await pre_call(client, from_number))

    assert context == {"caller_status": "unknown", "is_registered": False}
    call = await session.scalar(select(CallSession))
    assert call is not None and call.elder_id is None


async def test_blocked_caller_is_treated_as_unknown(
    client: AsyncClient, session: AsyncSession
) -> None:
    await add_elder(session, status=ElderStatus.BLOCKED)

    context = context_of(await pre_call(client))

    assert context == {"caller_status": "unknown", "is_registered": False}
    call = await session.scalar(select(CallSession))
    assert call is not None and call.elder_id is None


async def test_text_run_id_and_missing_run_id_are_accepted(
    client: AsyncClient, session: AsyncSession
) -> None:
    assert (await pre_call(client, run_id="run-abc")).status_code == 200
    assert (await pre_call(client, run_id=None)).status_code == 200

    run_ids = set(await session.scalars(select(CallSession.workflow_run_id)))
    assert run_ids == {"run-abc", None}


@pytest.mark.parametrize(
    "headers", [{}, {"Authorization": "Bearer wrong-key"}, {"Authorization": "test-dograh-key"}]
)
async def test_missing_or_wrong_api_key_is_rejected(
    client: AsyncClient, session: AsyncSession, headers: dict[str, str]
) -> None:
    response = await pre_call(client, headers=headers)

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"
    assert await session.scalar(select(CallSession)) is None


async def test_unconfigured_api_key_is_a_server_error(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    del app.dependency_overrides[get_dograh_api_key]
    monkeypatch.setattr(get_settings(), "dograh_api_key", "")

    response = await pre_call(client)

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "dograh_not_configured"
