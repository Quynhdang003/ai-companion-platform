from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient, Response
from sqlalchemy import inspect, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.llm.client import LLMError, get_scam_llm_client
from app.main import app
from app.models import (
    AlertStatus,
    AssessedBy,
    CallSession,
    ElderStatus,
    RiskLevel,
    ScamEvent,
    ScamType,
)
from app.services.scam.warnings import ADVICE
from tests.conftest import DOGRAH_HEADERS, add_elder, start_call
from tests.fakes import FakeLLMClient

# Decisive for layer 1 (credentials): high, no classifier call.
BANK_OTP = "Người xưng nhân viên ngân hàng xin bác đọc mã OTP vừa gửi về."
# Not decisive: a bank story and a threat (medium for layer 1).
BANK_LOCKED = "Có người xưng nhân viên ngân hàng gọi báo thẻ tín dụng của bác bị khóa."
# Not decisive: an investment offer with a money request (medium for layer 1).
INVESTMENT = "Có người mời bác góp vốn vào dự án đất nền."
HARMLESS = "Con trai bác gọi bằng số quen, bảo tối nay về ăn cơm."

MEDIUM_BANK = {"risk_level": "medium", "scam_type": "bank_impersonation", "signals": ["bank"]}


@pytest.fixture
def scam_llm(client: AsyncClient) -> FakeLLMClient:
    """The scam classifier the route uses (after `client` set its own): queue its replies."""
    llm = FakeLLMClient()
    app.dependency_overrides[get_scam_llm_client] = lambda: llm
    return llm


async def check(
    client: AsyncClient, token: str, situation: str, headers: dict[str, str] = DOGRAH_HEADERS
) -> Response:
    return await client.post(
        "/tools/check-scam", json={"session_token": token, "situation": situation}, headers=headers
    )


async def stored_events(session: AsyncSession) -> list[ScamEvent]:
    return list((await session.scalars(select(ScamEvent).order_by(ScamEvent.created_at))).all())


async def test_high_risk_is_stored_and_queues_a_family_alert(
    client: AsyncClient, session: AsyncSession, scam_llm: FakeLLMClient
) -> None:
    elder = await add_elder(session, status=ElderStatus.ACTIVE)
    token = await start_call(client)

    response = await check(client, token, BANK_OTP)

    assert response.status_code == 200
    body = response.json()
    assert (body["risk_level"], body["scam_type"]) == ("high", "bank_impersonation")
    assert body["message"].startswith("Dạ, chuyện này rất có thể là lừa đảo ạ.")
    assert ADVICE[ScamType.BANK_IMPERSONATION] in body["message"]
    assert scam_llm.prompts == []  # decided by a rule

    [event] = await stored_events(session)
    call = await session.scalar(select(CallSession).where(CallSession.elder_id == elder.id))
    assert (event.elder_id, event.call_session_id) == (elder.id, call.id)
    assert (event.scam_type, event.risk_level) == (ScamType.BANK_IMPERSONATION, RiskLevel.HIGH)
    assert (event.assessed_by, event.alert_status) == (AssessedBy.RULES, AlertStatus.PENDING)
    assert {"bank", "credentials"} <= set(event.signals)
    assert event.signals == sorted(event.signals)


async def test_medium_risk_is_stored_without_an_alert(
    client: AsyncClient, session: AsyncSession, scam_llm: FakeLLMClient
) -> None:
    await add_elder(session, status=ElderStatus.ACTIVE)
    token = await start_call(client)
    scam_llm.replies.append({"risk_level": "medium", "scam_type": "investment"})

    response = await check(client, token, INVESTMENT)

    body = response.json()
    assert (body["risk_level"], body["scam_type"]) == ("medium", "investment")
    assert body["message"].startswith("Dạ, chuyện này có dấu hiệu lừa đảo ạ.")
    [event] = await stored_events(session)
    assert (event.risk_level, event.assessed_by) == (RiskLevel.MEDIUM, AssessedBy.LLM)
    assert event.alert_status is None


@pytest.mark.parametrize("level", ["low", "none"])
async def test_low_and_no_risk_are_not_stored(
    client: AsyncClient, session: AsyncSession, scam_llm: FakeLLMClient, level: str
) -> None:
    await add_elder(session, status=ElderStatus.ACTIVE)
    token = await start_call(client)
    scam_llm.replies.append({"risk_level": level, "scam_type": None})

    response = await check(client, token, HARMLESS)

    assert response.json()["risk_level"] == level
    assert response.json()["scam_type"] is None
    assert response.json()["message"].startswith("Dạ, con chưa thấy dấu hiệu lừa đảo")
    assert await stored_events(session) == []


@pytest.mark.parametrize(
    ("status", "number"),
    [
        (ElderStatus.PENDING_VERIFICATION, "0912345678"),
        (ElderStatus.BLOCKED, "0912345678"),
        (None, "0912000009"),  # unregistered
    ],
    ids=["pending consent", "blocked", "unknown"],
)
async def test_callers_without_consent_are_warned_but_nothing_is_stored(
    client: AsyncClient,
    session: AsyncSession,
    scam_llm: FakeLLMClient,
    status: ElderStatus | None,
    number: str,
) -> None:
    if status is not None:
        await add_elder(session, status=status)
    token = await start_call(client, number)

    response = await check(client, token, BANK_OTP)

    assert response.status_code == 200
    assert response.json()["risk_level"] == "high"
    assert await stored_events(session) == []


async def test_consent_given_during_the_call_counts(
    client: AsyncClient, session: AsyncSession, scam_llm: FakeLLMClient
) -> None:
    await add_elder(session, status=ElderStatus.PENDING_VERIFICATION)
    token = await start_call(client)
    await client.post(
        "/tools/confirm-activation", json={"session_token": token}, headers=DOGRAH_HEADERS
    )

    await check(client, token, BANK_OTP)

    assert len(await stored_events(session)) == 1


async def test_one_event_per_call_and_type_whose_level_only_goes_up(
    client: AsyncClient, session: AsyncSession, scam_llm: FakeLLMClient
) -> None:
    await add_elder(session, status=ElderStatus.ACTIVE)
    token = await start_call(client)
    scam_llm.replies += [MEDIUM_BANK, MEDIUM_BANK]

    await check(client, token, BANK_LOCKED)  # medium
    [event] = await stored_events(session)
    assert (event.risk_level, event.alert_status) == (RiskLevel.MEDIUM, None)

    await check(client, token, BANK_OTP)  # high: the alert is queued
    [event] = await stored_events(session)
    assert (event.risk_level, event.alert_status) == (RiskLevel.HIGH, AlertStatus.PENDING)
    assert event.assessed_by is AssessedBy.RULES
    assert {"bank", "threat", "credentials"} <= set(event.signals)
    assert len(event.signals) == len(set(event.signals))

    # The alert went out; a later medium check lowers nothing and queues nothing.
    await session.execute(update(ScamEvent).values(alert_status=AlertStatus.SENT))
    await check(client, token, BANK_LOCKED)
    await check(client, token, BANK_OTP)
    [event] = await stored_events(session)
    assert (event.risk_level, event.alert_status) == (RiskLevel.HIGH, AlertStatus.SENT)


async def test_another_type_in_the_same_call_is_its_own_event(
    client: AsyncClient, session: AsyncSession, scam_llm: FakeLLMClient
) -> None:
    await add_elder(session, status=ElderStatus.ACTIVE)
    token = await start_call(client)
    scam_llm.replies.append({"risk_level": "medium", "scam_type": "investment"})

    await check(client, token, BANK_OTP)
    await check(client, token, INVESTMENT)

    events = await stored_events(session)
    assert {e.scam_type for e in events} == {ScamType.BANK_IMPERSONATION, ScamType.INVESTMENT}


async def test_classifier_failure_still_warns_from_the_rules(
    client: AsyncClient, session: AsyncSession, scam_llm: FakeLLMClient
) -> None:
    await add_elder(session, status=ElderStatus.ACTIVE)
    token = await start_call(client)
    scam_llm.replies.append(LLMError("Gemini API error 503"))

    response = await check(client, token, BANK_LOCKED)

    assert response.status_code == 200
    assert (response.json()["risk_level"], response.json()["scam_type"]) == (
        "medium",
        "bank_impersonation",
    )
    [event] = await stored_events(session)
    assert event.assessed_by is AssessedBy.RULES_FALLBACK


def test_no_column_can_hold_what_the_caller_said() -> None:
    columns = {column.key for column in inspect(ScamEvent).columns}

    assert columns == {
        "id",
        "call_session_id",
        "elder_id",
        "scam_type",
        "risk_level",
        "signals",
        "assessed_by",
        "alert_status",
        "alert_attempts",
        "alerted_at",
        "created_at",
        "updated_at",
    }


async def test_expired_session_is_rejected(
    client: AsyncClient, session: AsyncSession, scam_llm: FakeLLMClient
) -> None:
    await add_elder(session, status=ElderStatus.ACTIVE)
    token = await start_call(client)
    await session.execute(
        update(CallSession).values(expires_at=datetime.now(UTC) - timedelta(minutes=1))
    )

    response = await check(client, token, BANK_OTP)

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_session"
    assert await stored_events(session) == []


async def test_unknown_token_is_rejected(client: AsyncClient, scam_llm: FakeLLMClient) -> None:
    response = await check(client, "not-a-token", BANK_OTP)

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_session"


async def test_api_key_is_required(client: AsyncClient, scam_llm: FakeLLMClient) -> None:
    token = await start_call(client)

    response = await check(client, token, BANK_OTP, headers={})

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


@pytest.mark.parametrize(
    "body",
    [{}, {"situation": ""}, {"situation": "   "}, {"situation": "x" * 1001}],
    ids=["missing", "empty", "blank", "too long"],
)
async def test_situation_is_validated(
    client: AsyncClient, scam_llm: FakeLLMClient, body: dict[str, str]
) -> None:
    token = await start_call(client)

    response = await client.post(
        "/tools/check-scam", json={"session_token": token, **body}, headers=DOGRAH_HEADERS
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
