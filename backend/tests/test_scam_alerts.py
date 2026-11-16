import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.scheduler import start_scheduler
from app.models import (
    AlertStatus,
    AssessedBy,
    CallSession,
    Elder,
    ElderFamily,
    ElderStatus,
    FamilyRole,
    RiskLevel,
    ScamEvent,
    ScamType,
    TelegramLink,
    User,
)
from app.services.notification.channel import NotificationError, RecipientUnreachableError
from app.services.notification.messages import SCAM_TYPE_LABELS, scam_alert
from app.services.notification.scam_alerts import MAX_ATTEMPTS, process_next, run_alert_job
from tests.conftest import DOGRAH_HEADERS, add_elder, same_session, start_call
from tests.fakes import FakeTelegramBot

# 14:32 on 10 November in Vietnam (UTC+7).
WARNED_AT = datetime(2026, 11, 10, 7, 32, tzinfo=UTC)


@pytest.fixture
def bot() -> FakeTelegramBot:
    return FakeTelegramBot()


@pytest.fixture
async def elder(session: AsyncSession) -> Elder:
    return await add_elder(session, status=ElderStatus.ACTIVE)


async def owner_of(session: AsyncSession, elder: Elder) -> User:
    user = await session.scalar(
        select(User)
        .join(ElderFamily, ElderFamily.user_id == User.id)
        .where(ElderFamily.elder_id == elder.id, ElderFamily.role == FamilyRole.OWNER)
    )
    assert user is not None
    return user


async def add_viewer(session: AsyncSession, elder: Elder) -> User:
    user = User(clerk_user_id=f"user_viewer_{uuid.uuid4().hex[:8]}")
    session.add(user)
    await session.flush()
    session.add(ElderFamily(elder_id=elder.id, user_id=user.id, role=FamilyRole.VIEWER))
    await session.flush()
    return user


async def connect(session: AsyncSession, user: User, chat_id: int | None) -> None:
    """`chat_id=None`: asked for a link but never pressed Start."""
    session.add(
        TelegramLink(
            user_id=user.id,
            chat_id=chat_id,
            linked_at=datetime.now(UTC) if chat_id else None,
            link_token_hash=None if chat_id else uuid.uuid4().hex,
        )
    )
    await session.flush()


async def add_event(
    session: AsyncSession,
    elder: Elder,
    *,
    status: AlertStatus | None = AlertStatus.PENDING,
    scam_type: ScamType = ScamType.POLICE_IMPERSONATION,
    created_at: datetime | None = None,
) -> ScamEvent:
    call = CallSession(
        elder_id=elder.id,
        session_token_hash=uuid.uuid4().hex,
        from_number=elder.phone_e164,
        expires_at=datetime.now(UTC) + timedelta(hours=2),
    )
    session.add(call)
    await session.flush()
    event = ScamEvent(
        call_session_id=call.id,
        elder_id=elder.id,
        scam_type=scam_type,
        risk_level=RiskLevel.HIGH if status else RiskLevel.MEDIUM,
        signals=["authority", "money_transfer"],
        assessed_by=AssessedBy.RULES,
        alert_status=status,
    )
    if created_at:
        event.created_at = created_at
    session.add(event)
    await session.flush()
    return event


async def reload(session: AsyncSession, event: ScamEvent) -> ScamEvent:
    await session.refresh(event)
    return event


async def backdate_last_try(session: AsyncSession, event: ScamEvent) -> None:
    """Let the retry delay pass: in a test, now() is fixed for the whole transaction."""
    await session.execute(
        update(ScamEvent)
        .where(ScamEvent.id == event.id)
        .values(updated_at=datetime.now(UTC) - timedelta(minutes=5))
    )


def test_alert_names_the_elder_type_level_and_vietnam_time() -> None:
    text = scam_alert("Nguyễn Thị Lan", ScamType.BANK_IMPERSONATION, RiskLevel.HIGH, WARNED_AT)

    assert "Người thân: Nguyễn Thị Lan" in text
    assert "Kiểu lừa đảo: Giả danh nhân viên ngân hàng" in text
    assert "Mức nguy cơ: Cao" in text
    assert "Thời gian: 14:32 ngày 10/11/2026" in text


def test_every_scam_type_has_a_label() -> None:
    assert set(SCAM_TYPE_LABELS) == set(ScamType)


async def test_alerts_every_family_member_on_telegram_once(
    session: AsyncSession, elder: Elder, bot: FakeTelegramBot
) -> None:
    await connect(session, await owner_of(session, elder), 42)
    await connect(session, await add_viewer(session, elder), 43)
    await connect(session, await add_viewer(session, elder), 43)  # shares a chat
    await connect(session, await add_viewer(session, elder), None)  # never pressed Start
    await add_viewer(session, elder)  # no Telegram
    other = await add_elder(session, status=ElderStatus.ACTIVE, phone_e164="+84912000002")
    await connect(session, await owner_of(session, other), 99)
    event = await add_event(session, elder)

    assert await process_next(session, bot) is True

    assert sorted(chat for chat, _ in bot.sent) == ["42", "43"]
    text = bot.sent[0][1]
    assert "Nguyễn Thị Lan" in text and SCAM_TYPE_LABELS[ScamType.POLICE_IMPERSONATION] in text
    # Signal codes and anything else from the check stay out of the message.
    assert "authority" not in text and "money_transfer" not in text
    event = await reload(session, event)
    assert event.alert_status is AlertStatus.SENT and event.alerted_at is not None
    assert await process_next(session, bot) is False


async def test_nobody_on_telegram_skips_the_alert(
    session: AsyncSession, elder: Elder, bot: FakeTelegramBot
) -> None:
    await connect(session, await owner_of(session, elder), None)
    event = await add_event(session, elder)

    assert await process_next(session, bot) is True

    assert bot.sent == []
    assert (await reload(session, event)).alert_status is AlertStatus.SKIPPED


async def test_old_events_and_inactive_elders_are_skipped(
    session: AsyncSession, elder: Elder, bot: FakeTelegramBot
) -> None:
    await connect(session, await owner_of(session, elder), 42)
    old = await add_event(session, elder, created_at=datetime.now(UTC) - timedelta(hours=2))
    blocked = await add_elder(session, status=ElderStatus.BLOCKED, phone_e164="+84912000003")
    await connect(session, await owner_of(session, blocked), 43)
    from_blocked = await add_event(session, blocked)

    assert await run_alert_job(bot, same_session(session)) == 2

    assert bot.sent == []
    assert (await reload(session, old)).alert_status is AlertStatus.SKIPPED
    assert (await reload(session, from_blocked)).alert_status is AlertStatus.SKIPPED


async def test_only_pending_events_are_alerted(
    session: AsyncSession, elder: Elder, bot: FakeTelegramBot
) -> None:
    await connect(session, await owner_of(session, elder), 42)
    for status in (None, AlertStatus.SENT, AlertStatus.FAILED, AlertStatus.SKIPPED):
        await add_event(session, elder, status=status)

    assert await process_next(session, bot) is False
    assert bot.sent == []


async def test_a_chat_that_blocked_the_bot_is_disconnected(
    session: AsyncSession, elder: Elder, bot: FakeTelegramBot
) -> None:
    owner, viewer = await owner_of(session, elder), await add_viewer(session, elder)
    await connect(session, owner, 42)
    await connect(session, viewer, 43)
    bot.send_errors["42"] = RecipientUnreachableError("Telegram sendMessage: error 403")
    event = await add_event(session, elder)

    await process_next(session, bot)

    assert bot.sent[0][0] == "43"
    assert (await reload(session, event)).alert_status is AlertStatus.SENT
    linked = await session.scalars(select(TelegramLink.user_id))
    assert set(linked) == {viewer.id}


async def test_every_chat_unreachable_skips_the_alert(
    session: AsyncSession, elder: Elder, bot: FakeTelegramBot
) -> None:
    await connect(session, await owner_of(session, elder), 42)
    bot.send_errors["42"] = RecipientUnreachableError("Telegram sendMessage: error 403")
    event = await add_event(session, elder)

    await process_next(session, bot)

    assert (await reload(session, event)).alert_status is AlertStatus.SKIPPED
    assert await session.scalar(select(TelegramLink)) is None


async def test_one_failed_send_is_not_retried_once_someone_got_it(
    session: AsyncSession, elder: Elder, bot: FakeTelegramBot
) -> None:
    await connect(session, await owner_of(session, elder), 42)
    await connect(session, await add_viewer(session, elder), 43)
    bot.send_errors["42"] = NotificationError("Telegram sendMessage: error 502")
    event = await add_event(session, elder)

    await process_next(session, bot)

    assert [chat for chat, _ in bot.sent] == ["43"]
    event = await reload(session, event)
    assert event.alert_status is AlertStatus.SENT and event.alert_attempts == 0


async def test_failed_sends_are_retried_later_then_marked_failed(
    session: AsyncSession, elder: Elder, bot: FakeTelegramBot
) -> None:
    await connect(session, await owner_of(session, elder), 42)
    bot.send_errors["42"] = NotificationError("Telegram sendMessage: error 502")
    event = await add_event(session, elder)

    assert await process_next(session, bot) is True
    event = await reload(session, event)
    assert (event.alert_status, event.alert_attempts) == (AlertStatus.PENDING, 1)
    # Not again before the retry delay.
    assert await process_next(session, bot) is False

    for _ in range(MAX_ATTEMPTS - 1):
        await backdate_last_try(session, event)
        assert await process_next(session, bot) is True

    event = await reload(session, event)
    assert (event.alert_status, event.alert_attempts) == (AlertStatus.FAILED, MAX_ATTEMPTS)


async def test_a_retry_that_goes_through_is_sent(
    session: AsyncSession, elder: Elder, bot: FakeTelegramBot
) -> None:
    await connect(session, await owner_of(session, elder), 42)
    bot.send_errors["42"] = NotificationError("Telegram sendMessage: error 502")
    event = await add_event(session, elder)
    await process_next(session, bot)

    del bot.send_errors["42"]
    await backdate_last_try(session, event)
    await process_next(session, bot)

    event = await reload(session, event)
    assert event.alert_status is AlertStatus.SENT and len(bot.sent) == 1


async def test_job_run_takes_the_oldest_first_up_to_a_batch(
    session: AsyncSession, elder: Elder, bot: FakeTelegramBot
) -> None:
    await connect(session, await owner_of(session, elder), 42)
    now = datetime.now(UTC)
    for minutes, scam_type in [(3, ScamType.INVESTMENT), (9, ScamType.FAKE_CHARITY)]:
        await add_event(
            session, elder, scam_type=scam_type, created_at=now - timedelta(minutes=minutes)
        )
    await add_event(session, elder, scam_type=ScamType.OTHER, created_at=now - timedelta(minutes=1))

    assert await run_alert_job(bot, same_session(session), batch_size=2) == 2

    [(_, first), (_, second)] = bot.sent
    assert SCAM_TYPE_LABELS[ScamType.FAKE_CHARITY] in first
    assert SCAM_TYPE_LABELS[ScamType.INVESTMENT] in second
    assert await run_alert_job(bot, same_session(session)) == 1


async def test_a_high_risk_check_in_a_call_reaches_the_family(
    client: AsyncClient, session: AsyncSession, elder: Elder, bot: FakeTelegramBot
) -> None:
    await connect(session, await owner_of(session, elder), 42)
    token = await start_call(client)
    situation = "Người xưng nhân viên ngân hàng xin bác đọc mã OTP vừa gửi về."

    response = await client.post(
        "/tools/check-scam",
        json={"session_token": token, "situation": situation},
        headers=DOGRAH_HEADERS,
    )
    await process_next(session, bot)

    assert response.json()["risk_level"] == "high"
    [(chat, text)] = bot.sent
    assert chat == "42"
    assert SCAM_TYPE_LABELS[ScamType.BANK_IMPERSONATION] in text
    # Nothing the caller said reaches the family.
    assert "OTP" not in text

    # The same scam told again in this call: one event, already alerted.
    await client.post(
        "/tools/check-scam",
        json={"session_token": token, "situation": situation},
        headers=DOGRAH_HEADERS,
    )
    assert await process_next(session, bot) is False
    assert len(bot.sent) == 1


async def test_scheduler_sends_alerts_only_with_a_bot_token() -> None:
    without_token = start_scheduler(Settings(scheduler_enabled=True, telegram_bot_token=""))
    with_token = start_scheduler(Settings(scheduler_enabled=True, telegram_bot_token="1:x"))
    try:
        assert without_token is not None and without_token.get_job("scam_alerts") is None
        assert with_token is not None and with_token.get_job("scam_alerts") is not None
    finally:
        for scheduler in (without_token, with_token):
            if scheduler is not None:
                scheduler.shutdown(wait=False)
