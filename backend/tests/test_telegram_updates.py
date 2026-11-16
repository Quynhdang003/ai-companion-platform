from datetime import timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.scheduler import start_scheduler
from app.models import TelegramLink, User
from app.services.notification import telegram_links
from app.services.notification.channel import NotificationError
from app.services.notification.telegram import TelegramUpdate
from app.services.notification.telegram_updates import (
    HELP,
    LINK_INVALID,
    LINKED,
    TelegramUpdatePoller,
    handle_update,
)
from tests.conftest import same_session
from tests.fakes import FakeTelegramBot, private_message

TTL = timedelta(minutes=15)


@pytest.fixture
def bot() -> FakeTelegramBot:
    return FakeTelegramBot()


async def add_user(session: AsyncSession, name: str = "hoa") -> User:
    user = User(clerk_user_id=f"user_{name}")
    session.add(user)
    await session.flush()
    return user


async def connect_token(session: AsyncSession, user: User, ttl: timedelta = TTL) -> str:
    link = await telegram_links.create_link(session, user, bot_username="bot", ttl=ttl)
    return link.url.split("?start=")[1]


async def chat_of(session: AsyncSession, user: User) -> int | None:
    return await session.scalar(
        select(TelegramLink.chat_id)
        .where(TelegramLink.user_id == user.id)
        .execution_options(populate_existing=True)
    )


async def test_start_with_a_live_token_links_the_chat(
    session: AsyncSession, bot: FakeTelegramBot
) -> None:
    hoa = await add_user(session)
    token = await connect_token(session, hoa)

    await handle_update(session, bot, private_message(1, 42, f"/start {token}"))

    assert await chat_of(session, hoa) == 42
    assert bot.sent == [("42", LINKED)]


async def test_a_token_works_once(session: AsyncSession, bot: FakeTelegramBot) -> None:
    hoa = await add_user(session)
    token = await connect_token(session, hoa)

    await handle_update(session, bot, private_message(1, 42, f"/start {token}"))
    await handle_update(session, bot, private_message(2, 99, f"/start {token}"))

    assert await chat_of(session, hoa) == 42
    assert bot.sent[1] == ("99", LINK_INVALID)


async def test_expired_or_unknown_tokens_link_nothing(
    session: AsyncSession, bot: FakeTelegramBot
) -> None:
    hoa = await add_user(session)
    expired = await connect_token(session, hoa, ttl=timedelta(minutes=-1))

    await handle_update(session, bot, private_message(1, 42, f"/start {expired}"))
    await handle_update(session, bot, private_message(2, 42, "/start not-a-real-token"))

    assert await chat_of(session, hoa) is None
    assert bot.sent == [("42", LINK_INVALID), ("42", LINK_INVALID)]


async def test_command_addressed_to_the_bot_by_name(
    session: AsyncSession, bot: FakeTelegramBot
) -> None:
    hoa = await add_user(session)
    token = await connect_token(session, hoa)

    await handle_update(session, bot, private_message(1, 42, f"/start@test_alert_bot  {token} "))

    assert await chat_of(session, hoa) == 42


@pytest.mark.parametrize("text", ["/start", "xin chào", "/help", "start abc"])
async def test_other_messages_get_help(
    session: AsyncSession, bot: FakeTelegramBot, text: str
) -> None:
    await handle_update(session, bot, private_message(1, 42, text))

    assert bot.sent == [("42", HELP)]


async def test_group_chats_and_non_text_updates_are_ignored(
    session: AsyncSession, bot: FakeTelegramBot
) -> None:
    hoa = await add_user(session)
    token = await connect_token(session, hoa)
    group = {"chat": {"id": -100, "type": "group"}, "text": f"/start {token}"}
    sticker = {"chat": {"id": 42, "type": "private"}}

    for update in [
        {"update_id": 1, "message": group},
        {"update_id": 2, "message": sticker},
        {"update_id": 3},  # not a message
    ]:
        await handle_update(session, bot, TelegramUpdate.model_validate(update))

    assert await chat_of(session, hoa) is None
    assert bot.sent == []


async def test_connecting_another_chat_replaces_the_old_one(
    session: AsyncSession, bot: FakeTelegramBot
) -> None:
    hoa = await add_user(session)
    await handle_update(
        session, bot, private_message(1, 42, f"/start {await connect_token(session, hoa)}")
    )

    await handle_update(
        session, bot, private_message(2, 77, f"/start {await connect_token(session, hoa)}")
    )

    assert await chat_of(session, hoa) == 77


async def test_two_accounts_may_share_a_chat(session: AsyncSession, bot: FakeTelegramBot) -> None:
    hoa, nam = await add_user(session, "hoa"), await add_user(session, "nam")

    for user in (hoa, nam):
        token = await connect_token(session, user)
        await handle_update(session, bot, private_message(1, 42, f"/start {token}"))

    assert await chat_of(session, hoa) == 42 and await chat_of(session, nam) == 42


async def test_a_lost_reply_keeps_the_link(session: AsyncSession, bot: FakeTelegramBot) -> None:
    hoa = await add_user(session)
    bot.send_errors["42"] = NotificationError("Telegram sendMessage: error 502")

    await handle_update(
        session, bot, private_message(1, 42, f"/start {await connect_token(session, hoa)}")
    )

    assert await chat_of(session, hoa) == 42


async def test_poller_confirms_what_it_handled(session: AsyncSession, bot: FakeTelegramBot) -> None:
    hoa = await add_user(session)
    token = await connect_token(session, hoa)
    bot.updates = [
        [private_message(10, 42, "xin chào"), private_message(11, 42, f"/start {token}")],
        [],
    ]
    poller = TelegramUpdatePoller(bot, same_session(session))

    assert await poller.run_once() == 2
    assert await poller.run_once() == 0

    assert bot.offsets == [None, 12]
    assert await chat_of(session, hoa) == 42


async def test_poller_survives_telegram_errors(session: AsyncSession, bot: FakeTelegramBot) -> None:
    bot.updates = [
        NotificationError("Telegram getUpdates: error 502"),
        [private_message(5, 42, "hi")],
    ]
    poller = TelegramUpdatePoller(bot, same_session(session))

    assert await poller.run_once() == 0
    assert await poller.run_once() == 1
    assert await poller.run_once() == 0

    assert bot.offsets == [None, None, 6]


async def test_scheduler_polls_telegram_only_with_a_bot_token() -> None:
    without_token = start_scheduler(Settings(scheduler_enabled=True, telegram_bot_token=""))
    with_token = start_scheduler(Settings(scheduler_enabled=True, telegram_bot_token="1:x"))
    try:
        assert without_token is not None and without_token.get_job("telegram_updates") is None
        assert with_token is not None and with_token.get_job("telegram_updates") is not None
    finally:
        for scheduler in (without_token, with_token):
            if scheduler is not None:
                scheduler.shutdown(wait=False)
