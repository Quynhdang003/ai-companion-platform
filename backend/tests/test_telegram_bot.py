import json
from collections.abc import Callable

import httpx
import pytest

from app.services.notification.channel import NotificationError, RecipientUnreachableError
from app.services.notification.telegram import TelegramBot, TelegramNotConfiguredError

TOKEN = "123456:secret-bot-token"
Handler = Callable[[httpx.Request], httpx.Response]


def bot_with(handler: Handler, token: str = TOKEN) -> tuple[TelegramBot, list[httpx.Request]]:
    requests: list[httpx.Request] = []

    def record(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return handler(request)

    return TelegramBot(token, transport=httpx.MockTransport(record)), requests


def ok(result: object) -> Handler:
    return lambda _: httpx.Response(200, json={"ok": True, "result": result})


def api_error(code: int, description: str) -> Handler:
    body = {"ok": False, "error_code": code, "description": description}
    return lambda _: httpx.Response(code, json=body)


async def test_send_posts_plain_text_to_the_chat() -> None:
    bot, requests = bot_with(ok({"message_id": 1}))

    await bot.send("42", "Cảnh báo lừa đảo")

    [request] = requests
    assert request.method == "POST"
    assert str(request.url) == f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    assert json.loads(request.content) == {"chat_id": "42", "text": "Cảnh báo lừa đảo"}


async def test_get_updates_reads_messages_from_the_offset() -> None:
    result = [
        {
            "update_id": 7,
            "message": {
                "message_id": 1,
                "date": 1_700_000_000,
                "from": {"id": 42, "is_bot": False, "first_name": "Hoa"},
                "chat": {"id": 42, "type": "private", "first_name": "Hoa"},
                "text": "/start abc",
            },
        },
        {"update_id": 8, "edited_message": {"chat": {"id": 42, "type": "private"}}},
    ]
    bot, requests = bot_with(ok(result))

    updates = await bot.get_updates(7)

    assert json.loads(requests[0].content) == {
        "offset": 7,
        "timeout": 0,
        "allowed_updates": ["message"],
    }
    assert [u.update_id for u in updates] == [7, 8]
    first = updates[0].message
    assert first is not None and first.chat.id == 42 and first.text == "/start abc"
    assert updates[1].message is None


async def test_first_get_updates_sends_no_offset() -> None:
    bot, requests = bot_with(ok([]))

    assert await bot.get_updates(None) == []
    assert "offset" not in json.loads(requests[0].content)


@pytest.mark.parametrize(
    "handler",
    [
        api_error(403, "Forbidden: bot was blocked by the user"),
        api_error(403, "Forbidden: user is deactivated"),
        api_error(400, "Bad Request: chat not found"),
    ],
)
async def test_chats_that_cannot_get_messages_are_unreachable(handler: Handler) -> None:
    bot, _ = bot_with(handler)

    with pytest.raises(RecipientUnreachableError):
        await bot.send("42", "x")


@pytest.mark.parametrize(
    "handler",
    [
        api_error(429, "Too Many Requests: retry after 5"),
        api_error(400, "Bad Request: message is too long"),
        lambda _: httpx.Response(502, text="<html>Bad Gateway</html>"),
        ok("not a list"),
    ],
)
async def test_other_failures_are_worth_retrying(handler: Handler) -> None:
    bot, _ = bot_with(handler)

    with pytest.raises(NotificationError) as info:
        await bot.get_updates(None)

    assert not isinstance(info.value, RecipientUnreachableError)
    assert TOKEN not in str(info.value)


async def test_network_errors_never_carry_the_url() -> None:
    def unreachable(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(f"cannot reach {request.url}", request=request)

    bot, _ = bot_with(unreachable)

    with pytest.raises(NotificationError) as info:
        await bot.send("42", "x")

    assert TOKEN not in str(info.value)
    # Nothing chained either: a logged traceback would print the httpx error with the URL.
    assert info.value.__cause__ is None and info.value.__suppress_context__


async def test_without_a_token_nothing_is_sent() -> None:
    bot, requests = bot_with(ok({"message_id": 1}), token="")

    with pytest.raises(TelegramNotConfiguredError):
        await bot.send("42", "x")
    assert requests == []
