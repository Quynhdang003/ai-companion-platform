"""The ride update job: the family hears what the elder chose to share, and nothing else."""

from datetime import timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.scheduler import start_scheduler
from app.models import (
    AlertStatus,
    Elder,
    ElderStatus,
    RideEvent,
    RideNotification,
    RideStatus,
)
from app.services.notification.channel import NotificationError
from app.services.notification.messages import VN_TZ
from app.services.notification.ride_alerts import MAX_ATTEMPTS, process_next, run_ride_alert_job
from tests.conftest import add_elder, same_session, start_call
from tests.fakes import FakeRideProvider, FakeTelegramBot
from tests.ride_helpers import BACH_MAI, LANG_HA, book_trip, ride_tool
from tests.test_scam_alerts import add_viewer, connect, owner_of

pytestmark = pytest.mark.usefixtures("no_confirm_wait")

OWNER_CHAT, VIEWER_CHAT = 111, 222


@pytest.fixture
def bot() -> FakeTelegramBot:
    return FakeTelegramBot()


@pytest.fixture
async def elder(session: AsyncSession) -> Elder:
    """An ACTIVE elder whose owner and a viewer connected Telegram."""
    elder = await add_elder(session, status=ElderStatus.ACTIVE)
    await connect(session, await owner_of(session, elder), OWNER_CHAT)
    await connect(session, await add_viewer(session, elder), VIEWER_CHAT)
    return elder


@pytest.fixture
async def token(client: AsyncClient, elder: Elder) -> str:
    return await start_call(client)


async def booked(client: AsyncClient, rides: FakeRideProvider, token: str) -> str:
    """Book Lang Ha -> Bach Mai by car4; the provider's booking id."""
    await book_trip(client, rides, token, LANG_HA, BACH_MAI)
    [ride] = rides.bookings
    return ride


async def share(client: AsyncClient, token: str, scope: str) -> None:
    response = await ride_tool(client, "set-ride-sharing", token, scope=scope)
    assert response.status_code == 200


async def move(
    client: AsyncClient, rides: FakeRideProvider, token: str, ride: str, status: RideStatus, **kw
) -> None:
    """The provider moves the ride on, and the elder asks about it."""
    rides.move(ride, status, **kw)
    assert (await ride_tool(client, "get-ride-status", token)).status_code == 200


async def run(session: AsyncSession, bot: FakeTelegramBot) -> int:
    return await run_ride_alert_job(bot, same_session(session))


async def statuses(session: AsyncSession) -> dict[RideEvent, AlertStatus]:
    rows = await session.execute(
        select(RideNotification.event, RideNotification.status).execution_options(
            populate_existing=True
        )
    )
    return {event: status for event, status in rows}


def sent_to(bot: FakeTelegramBot, chat: int) -> list[str]:
    return [text for recipient, text in bot.sent if recipient == str(chat)]


async def test_an_update_waits_for_the_elders_answer(
    client: AsyncClient,
    session: AsyncSession,
    rides: FakeRideProvider,
    bot: FakeTelegramBot,
    token: str,
) -> None:
    await booked(client, rides, token)

    # Asked right after booking: not answered yet.
    assert await run(session, bot) == 0
    assert await statuses(session) == {RideEvent.BOOKED: AlertStatus.PENDING}

    await share(client, token, "status")

    assert await run(session, bot) == 1
    assert await statuses(session) == {RideEvent.BOOKED: AlertStatus.SENT}
    assert len(sent_to(bot, OWNER_CHAT)) == len(sent_to(bot, VIEWER_CHAT)) == 1


async def test_an_update_never_answered_for_is_dropped(
    client: AsyncClient,
    session: AsyncSession,
    rides: FakeRideProvider,
    bot: FakeTelegramBot,
    token: str,
) -> None:
    await booked(client, rides, token)
    await session.execute(
        update(RideNotification).values(
            created_at=RideNotification.created_at - timedelta(minutes=16)
        )
    )

    assert await run(session, bot) == 1
    assert await statuses(session) == {RideEvent.BOOKED: AlertStatus.SKIPPED}
    assert bot.sent == []


async def test_status_sharing_says_what_and_when_but_not_where(
    client: AsyncClient,
    session: AsyncSession,
    rides: FakeRideProvider,
    bot: FakeTelegramBot,
    token: str,
) -> None:
    await share(client, token, "status")
    await booked(client, rides, token)

    await run(session, bot)

    note = await session.scalar(select(RideNotification))
    when = note.created_at.astimezone(VN_TZ).strftime("%H:%M ngày %d/%m/%Y")
    assert sent_to(bot, OWNER_CHAT) == [
        "🚕 Chuyến xe: Đã đặt xe\n"
        "Người thân: Nguyễn Thị Lan\n"
        "Loại xe: Xe bốn chỗ\n"
        f"Thời gian: {when}\n\n"
        "Người thân của bạn chọn chỉ chia sẻ trạng thái chuyến đi, không kèm địa điểm."
    ]
    assert sent_to(bot, VIEWER_CHAT) == sent_to(bot, OWNER_CHAT)


async def test_details_sharing_adds_the_places_and_the_car(
    client: AsyncClient,
    session: AsyncSession,
    rides: FakeRideProvider,
    bot: FakeTelegramBot,
    token: str,
) -> None:
    await share(client, token, "details")
    ride = await booked(client, rides, token)
    await move(client, rides, token, ride, RideStatus.IN_PROGRESS)

    await run(session, bot)

    booked_text, boarded_text = sent_to(bot, OWNER_CHAT)
    assert booked_text.startswith("🚕 Chuyến xe: Đã đặt xe\n")
    assert boarded_text.startswith("🚕 Chuyến xe: Đã lên xe, đang trên đường\n")
    assert boarded_text.endswith(
        "Điểm đón: Ngõ 12 Phố Láng Hạ\n"
        "Điểm đến: Bệnh viện Bạch Mai (78 Đường Giải Phóng)\n"
        "Xe: Toyota Vios, biển số 30H-575.35"
    )
    assert "chỉ chia sẻ trạng thái" not in boarded_text


async def test_withdrawing_applies_at_once_also_to_a_ride_in_progress(
    client: AsyncClient,
    session: AsyncSession,
    rides: FakeRideProvider,
    bot: FakeTelegramBot,
    token: str,
) -> None:
    await share(client, token, "details")
    ride = await booked(client, rides, token)
    await run(session, bot)
    await move(client, rides, token, ride, RideStatus.IN_PROGRESS)

    # "Đừng báo nữa", while on the way.
    await share(client, await start_call(client), "none")
    await run(session, bot)

    assert await statuses(session) == {
        RideEvent.BOOKED: AlertStatus.SENT,
        RideEvent.ON_THE_WAY: AlertStatus.SKIPPED,
    }
    assert len(sent_to(bot, OWNER_CHAT)) == 1


async def test_nothing_shared_nothing_sent(
    client: AsyncClient,
    session: AsyncSession,
    rides: FakeRideProvider,
    bot: FakeTelegramBot,
    token: str,
) -> None:
    await share(client, token, "none")
    await booked(client, rides, token)

    assert await run(session, bot) == 1
    assert await statuses(session) == {RideEvent.BOOKED: AlertStatus.SKIPPED}
    assert bot.sent == []


async def test_a_cancellation_says_who_cancelled(
    client: AsyncClient,
    session: AsyncSession,
    rides: FakeRideProvider,
    bot: FakeTelegramBot,
    token: str,
) -> None:
    await share(client, token, "status")
    ride = await booked(client, rides, token)
    await move(client, rides, token, ride, RideStatus.CANCELLED, cancel_reason="driver")

    await run(session, bot)

    cancelled_text = sent_to(bot, OWNER_CHAT)[-1]
    assert cancelled_text.startswith("🚕 Chuyến xe: Chuyến xe đã bị hủy\n")
    assert "Người hủy: Tài xế\n" in cancelled_text


async def test_an_elder_no_longer_active_is_skipped(
    client: AsyncClient,
    session: AsyncSession,
    rides: FakeRideProvider,
    bot: FakeTelegramBot,
    elder: Elder,
    token: str,
) -> None:
    await share(client, token, "status")
    await booked(client, rides, token)
    await session.execute(
        update(Elder).where(Elder.id == elder.id).values(status=ElderStatus.BLOCKED)
    )

    await run(session, bot)

    assert await statuses(session) == {RideEvent.BOOKED: AlertStatus.SKIPPED}
    assert bot.sent == []


async def test_nobody_on_telegram(
    client: AsyncClient,
    session: AsyncSession,
    rides: FakeRideProvider,
    bot: FakeTelegramBot,
) -> None:
    await add_elder(session, status=ElderStatus.ACTIVE)
    token = await start_call(client)
    await share(client, token, "status")
    await booked(client, rides, token)

    await run(session, bot)

    assert await statuses(session) == {RideEvent.BOOKED: AlertStatus.SKIPPED}


async def test_failed_sends_are_retried_later_then_marked_failed(
    client: AsyncClient,
    session: AsyncSession,
    rides: FakeRideProvider,
    bot: FakeTelegramBot,
    token: str,
) -> None:
    await share(client, token, "status")
    await booked(client, rides, token)
    for chat in (OWNER_CHAT, VIEWER_CHAT):
        bot.send_errors[str(chat)] = NotificationError("Telegram sendMessage: error 500")

    assert await process_next(session, bot) is True
    # Not due again until the retry delay has passed.
    assert await process_next(session, bot) is False

    for _ in range(MAX_ATTEMPTS - 1):
        await session.execute(
            update(RideNotification).values(
                updated_at=RideNotification.updated_at - timedelta(seconds=31)
            )
        )
        assert await process_next(session, bot) is True

    note = await session.scalar(select(RideNotification).execution_options(populate_existing=True))
    assert (note.status, note.attempts) == (AlertStatus.FAILED, MAX_ATTEMPTS)


async def test_the_scheduler_sends_ride_updates_with_a_bot_token() -> None:
    with_token = start_scheduler(Settings(scheduler_enabled=True, telegram_bot_token="t"))
    without = start_scheduler(Settings(scheduler_enabled=True, telegram_bot_token=""))
    try:
        assert with_token is not None and with_token.get_job("ride_alerts") is not None
        assert without is not None and without.get_job("ride_alerts") is None
    finally:
        for scheduler in (with_token, without):
            if scheduler is not None:
                scheduler.shutdown(wait=False)
