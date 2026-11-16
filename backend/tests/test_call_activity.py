"""Family call activity: GET /api/elders/{id} and /calls. Metadata only, linked family only."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from httpx import AsyncClient, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    AssessedBy,
    CallLog,
    CallSession,
    Elder,
    ElderFamily,
    ElderLinkRequest,
    ElderStatus,
    FamilyRole,
    MemoryStatus,
    RiskLevel,
    ScamEvent,
    ScamType,
    User,
    UserRole,
)
from tests.conftest import HeadersFactory, add_elder

NOW = datetime.now(UTC)
CONSENT_AT = NOW - timedelta(days=40)


async def add_call(
    session: AsyncSession,
    elder: Elder | None,
    started_at: datetime,
    *,
    duration: int | None = None,
    scams: tuple[tuple[ScamType, RiskLevel], ...] = (),
) -> CallSession:
    """A call: its session, its log (with a transcript, which must never come out) and events."""
    call = CallSession(
        elder_id=elder.id if elder else None,
        session_token_hash=uuid.uuid4().hex,
        from_number=elder.phone_e164 if elder else "+84912000009",
        started_at=started_at,
        expires_at=started_at + timedelta(hours=2),
    )
    session.add(call)
    await session.flush()
    if duration is not None:
        session.add(
            CallLog(
                call_session_id=call.id,
                duration_seconds=duration,
                disposition="completed",
                transcript=[{"role": "elder", "text": "Bí mật của bà"}],
                recording_url="http://dograh/recording",
                memory_status=MemoryStatus.DONE,
            )
        )
    for minutes, (scam_type, level) in enumerate(scams, start=1):
        assert elder is not None
        session.add(
            ScamEvent(
                call_session_id=call.id,
                elder_id=elder.id,
                scam_type=scam_type,
                risk_level=level,
                signals=["credentials"],
                assessed_by=AssessedBy.RULES,
                created_at=started_at + timedelta(minutes=minutes),
            )
        )
    await session.flush()
    return call


async def user_id(client: AsyncClient, headers: dict[str, str]) -> uuid.UUID:
    """The user behind `headers` (created as family on their first request)."""
    response = await client.get("/api/me", headers=headers)
    return uuid.UUID(response.json()["id"])


async def owner_headers(
    session: AsyncSession, elder: Elder, auth_headers: HeadersFactory
) -> dict[str, str]:
    clerk_id = await session.scalar(
        select(User.clerk_user_id)
        .join(ElderFamily, ElderFamily.user_id == User.id)
        .where(ElderFamily.elder_id == elder.id, ElderFamily.role == FamilyRole.OWNER)
    )
    assert clerk_id is not None
    return auth_headers(clerk_id)


@pytest.fixture
async def elder(session: AsyncSession) -> Elder:
    """ACTIVE since 40 days ago."""
    elder = await add_elder(session, status=ElderStatus.ACTIVE)
    elder.consent_at = CONSENT_AT
    await session.flush()
    return elder


@pytest.fixture
async def headers(
    session: AsyncSession, elder: Elder, auth_headers: HeadersFactory
) -> dict[str, str]:
    """The elder's owner."""
    return await owner_headers(session, elder, auth_headers)


async def get(client: AsyncClient, path: str, headers: dict[str, str], **params: Any) -> Response:
    return await client.get(path, headers=headers, params=params)


async def calls_of(
    client: AsyncClient, elder: Elder, headers: dict[str, str], **params: Any
) -> dict[str, Any]:
    response = await get(client, f"/api/elders/{elder.id}/calls", headers, **params)
    assert response.status_code == 200, response.text
    return response.json()


def ids(body: dict[str, Any]) -> list[str]:
    return [call["id"] for call in body["calls"]]


# Who may see it


async def test_owner_and_viewers_see_the_elder(
    client: AsyncClient,
    session: AsyncSession,
    elder: Elder,
    headers: dict[str, str],
    auth_headers: HeadersFactory,
) -> None:
    viewer = auth_headers("user_viewer")
    session.add(
        ElderFamily(
            elder_id=elder.id,
            user_id=await user_id(client, viewer),
            role=FamilyRole.VIEWER,
        )
    )
    await session.flush()

    for who, role in ((headers, "owner"), (viewer, "viewer")):
        detail = await get(client, f"/api/elders/{elder.id}", who)
        assert (detail.status_code, detail.json()["my_role"]) == (200, role)
        assert (await get(client, f"/api/elders/{elder.id}/calls", who)).status_code == 200


async def test_anyone_else_gets_not_found(
    client: AsyncClient, session: AsyncSession, elder: Elder, auth_headers: HeadersFactory
) -> None:
    stranger = auth_headers("user_stranger")
    # A link request not approved yet gives no access either.
    requester = auth_headers("user_requester")
    session.add(ElderLinkRequest(elder_id=elder.id, requester_id=await user_id(client, requester)))
    await session.flush()

    for who in (stranger, requester):
        for path in (f"/api/elders/{elder.id}", f"/api/elders/{elder.id}/calls"):
            response = await get(client, path, who)
            assert response.status_code == 404, path
            assert response.json()["error"]["code"] == "not_found"
    # An id that doesn't exist answers the same.
    assert (await get(client, f"/api/elders/{uuid.uuid4()}", stranger)).status_code == 404


async def test_signed_out_admins_and_bad_ids_are_refused(
    client: AsyncClient, session: AsyncSession, elder: Elder, auth_headers: HeadersFactory
) -> None:
    session.add(User(clerk_user_id="user_admin", role=UserRole.ADMIN))
    await session.flush()

    assert (await client.get(f"/api/elders/{elder.id}")).status_code == 401
    assert (
        await get(client, f"/api/elders/{elder.id}", auth_headers("user_admin"))
    ).status_code == 403
    assert (await get(client, "/api/elders/not-a-uuid", auth_headers("u"))).status_code == 422


# What is shown


async def test_calls_show_time_duration_and_scam_alerts_only(
    client: AsyncClient, session: AsyncSession, elder: Elder, headers: dict[str, str]
) -> None:
    consent_call = await add_call(session, elder, CONSENT_AT - timedelta(minutes=1), duration=95)
    warned = await add_call(
        session,
        elder,
        NOW - timedelta(days=2),
        duration=300,
        scams=(
            (ScamType.BANK_IMPERSONATION, RiskLevel.HIGH),
            (ScamType.INVESTMENT, RiskLevel.MEDIUM),
        ),
    )
    ongoing = await add_call(session, elder, NOW - timedelta(minutes=3))

    body = await calls_of(client, elder, headers)

    assert ids(body) == [str(ongoing.id), str(warned.id), str(consent_call.id)]
    assert body["next_before"] is None
    newest, second, oldest = body["calls"]
    assert set(newest) == {"id", "started_at", "duration_seconds", "scam_alerts"}
    assert (newest["duration_seconds"], newest["scam_alerts"]) == (None, [])
    assert datetime.fromisoformat(second["started_at"]) == warned.started_at
    assert second["duration_seconds"] == 300
    assert [
        (a["scam_type"], a["risk_level"], datetime.fromisoformat(a["created_at"]))
        for a in second["scam_alerts"]
    ] == [
        ("bank_impersonation", "high", warned.started_at + timedelta(minutes=1)),
        ("investment", "medium", warned.started_at + timedelta(minutes=2)),
    ]
    assert set(second["scam_alerts"][0]) == {"scam_type", "risk_level", "created_at"}
    assert oldest["duration_seconds"] == 95
    # Nothing said in a call, no recording, no signal codes.
    for hidden in ("Bí mật", "recording", "credentials"):
        assert hidden not in str(body)


async def test_calls_before_the_consent_call_are_never_shown(
    client: AsyncClient, session: AsyncSession, elder: Elder, headers: dict[str, str]
) -> None:
    await add_call(session, elder, CONSENT_AT - timedelta(days=3), duration=40)  # declined
    await add_call(session, elder, CONSENT_AT - timedelta(hours=5), duration=20)  # undecided
    consent_call = await add_call(session, elder, CONSENT_AT - timedelta(minutes=2), duration=90)
    later = await add_call(session, elder, CONSENT_AT + timedelta(days=1), duration=60)

    assert ids(await calls_of(client, elder, headers)) == [str(later.id), str(consent_call.id)]


async def test_an_elder_who_never_consented_shows_no_calls(
    client: AsyncClient, session: AsyncSession, auth_headers: HeadersFactory
) -> None:
    pending = await add_elder(
        session, status=ElderStatus.PENDING_VERIFICATION, phone_e164="+84912000002"
    )
    await add_call(session, pending, NOW - timedelta(days=1), duration=60)
    headers = await owner_headers(session, pending, auth_headers)

    assert (await calls_of(client, pending, headers))["calls"] == []
    detail = (await get(client, f"/api/elders/{pending.id}", headers)).json()
    assert detail["consent_at"] is None
    assert detail["activity"] == {
        "calls_7d": 0,
        "calls_30d": 0,
        "scam_alerts_30d": 0,
        "last_call_at": None,
    }


async def test_other_callers_are_not_mixed_in(
    client: AsyncClient, session: AsyncSession, elder: Elder, headers: dict[str, str]
) -> None:
    other = await add_elder(session, status=ElderStatus.ACTIVE, phone_e164="+84912000002")
    other.consent_at = CONSENT_AT
    await add_call(session, other, NOW - timedelta(days=1))
    await add_call(session, None, NOW - timedelta(days=1))  # unknown caller
    own = await add_call(session, elder, NOW - timedelta(days=1))

    assert ids(await calls_of(client, elder, headers)) == [str(own.id)]


async def test_calls_come_a_page_at_a_time(
    client: AsyncClient, session: AsyncSession, elder: Elder, headers: dict[str, str]
) -> None:
    made = [await add_call(session, elder, NOW - timedelta(days=d)) for d in (1, 2, 3, 4, 5)]

    first = await calls_of(client, elder, headers, limit=2)
    second = await calls_of(client, elder, headers, limit=2, before=first["next_before"])
    third = await calls_of(client, elder, headers, limit=2, before=second["next_before"])

    assert ids(first) + ids(second) + ids(third) == [str(call.id) for call in made]
    assert third["next_before"] is None


@pytest.mark.parametrize(
    "params",
    [{"limit": 0}, {"limit": 51}, {"before": "2026-11-16T10:00:00"}, {"before": "yesterday"}],
    ids=["limit-0", "limit-51", "before-without-zone", "before-not-a-time"],
)
async def test_invalid_page_parameters_are_rejected(
    client: AsyncClient, elder: Elder, headers: dict[str, str], params: dict
) -> None:
    response = await get(client, f"/api/elders/{elder.id}/calls", headers, **params)

    assert response.status_code == 422


async def test_detail_counts_calls_and_scam_alerts(
    client: AsyncClient, session: AsyncSession, elder: Elder, headers: dict[str, str]
) -> None:
    await add_call(
        session, elder, NOW - timedelta(days=35), scams=((ScamType.OTHER, RiskLevel.HIGH),)
    )
    await add_call(session, elder, NOW - timedelta(days=10))
    await add_call(session, elder, NOW - timedelta(days=6))
    last = await add_call(
        session,
        elder,
        NOW - timedelta(hours=1),
        scams=((ScamType.FAKE_CHARITY, RiskLevel.MEDIUM), (ScamType.OTHER, RiskLevel.HIGH)),
    )

    response = await get(client, f"/api/elders/{elder.id}", headers)

    assert response.status_code == 200
    body = response.json()
    assert {key: body[key] for key in ("full_name", "status", "my_role")} == {
        "full_name": "Nguyễn Thị Lan",
        "status": "ACTIVE",
        "my_role": "owner",
    }
    assert datetime.fromisoformat(body["consent_at"]) == CONSENT_AT
    activity = body["activity"]
    assert (activity["calls_7d"], activity["calls_30d"], activity["scam_alerts_30d"]) == (2, 3, 2)
    assert datetime.fromisoformat(activity["last_call_at"]) == last.started_at
