from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient, Response
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dograh.tools import KNOWLEDGE_RESULTS
from app.llm.client import LLMError, get_llm_client
from app.main import app
from app.models import CallSession, ElderStatus
from app.services.rag.ingest import add_document
from tests.conftest import DOGRAH_HEADERS, add_elder, start_call
from tests.fakes import FakeLLMClient

EMERGENCY = "Số điện thoại khẩn cấp"
EMERGENCY_TEXT = (
    "Gọi 113 khi cần công an giúp đỡ. Gọi 114 khi có cháy nổ, cần cứu hỏa. "
    "Gọi 115 khi cần xe cấp cứu đưa người bệnh đi viện."
)
SCAMS = "Nhận biết cuộc gọi lừa đảo"
SCAMS_TEXT = "Ngân hàng không bao giờ hỏi mã OTP hay mật khẩu của khách hàng qua điện thoại."
NOT_FOUND = "Dạ, con chưa có thông tin về việc này ạ."


@pytest.fixture
async def kb(session: AsyncSession) -> None:
    llm = FakeLLMClient()
    await add_document(session, llm, title=EMERGENCY, content=EMERGENCY_TEXT)
    await add_document(session, llm, title=SCAMS, content=SCAMS_TEXT)


async def search(
    client: AsyncClient, token: str, query: str, headers: dict[str, str] = DOGRAH_HEADERS
) -> Response:
    return await client.post(
        "/tools/search-knowledge", json={"session_token": token, "query": query}, headers=headers
    )


async def test_question_without_diacritics_gets_the_passage(
    client: AsyncClient, session: AsyncSession, kb: None
) -> None:
    await add_elder(session, status=ElderStatus.ACTIVE)
    token = await start_call(client)

    response = await search(client, token, "goi xe cap cuu so may")

    assert response.status_code == 200
    body = response.json()
    assert body["found"] is True
    assert body["message"] == "Dạ, con tìm được thông tin rồi ạ."
    assert body["results"][0] == {"title": EMERGENCY, "content": EMERGENCY_TEXT}


async def test_unrelated_question_finds_nothing(
    client: AsyncClient, session: AsyncSession, kb: None
) -> None:
    await add_elder(session, status=ElderStatus.ACTIVE)
    token = await start_call(client)

    response = await search(client, token, "giá vàng hôm nay bao nhiêu")

    assert response.status_code == 200
    assert response.json() == {"found": False, "message": NOT_FOUND, "results": []}


async def test_blank_question_finds_nothing(
    client: AsyncClient, session: AsyncSession, kb: None
) -> None:
    token = await start_call(client)

    response = await search(client, token, "  ?! ")

    assert response.status_code == 200
    assert response.json()["found"] is False


async def test_embedding_failure_falls_back_to_lexical_search(
    client: AsyncClient, session: AsyncSession, kb: None
) -> None:
    failing = FakeLLMClient()
    failing.embed_error = LLMError("down")
    app.dependency_overrides[get_llm_client] = lambda: failing
    token = await start_call(client)

    response = await search(client, token, "ngân hàng hỏi mã OTP")

    assert response.status_code == 200
    assert response.json()["results"][0]["title"] == SCAMS


async def test_results_are_capped(client: AsyncClient, session: AsyncSession) -> None:
    llm = FakeLLMClient()
    for i in range(KNOWLEDGE_RESULTS + 2):
        await add_document(session, llm, title=f"Cấp cứu {i}", content=EMERGENCY_TEXT)
    token = await start_call(client)

    response = await search(client, token, "gọi cấp cứu")

    assert len(response.json()["results"]) == KNOWLEDGE_RESULTS


@pytest.mark.parametrize("status", [ElderStatus.PENDING_VERIFICATION, None])
async def test_callers_without_consent_can_search(
    client: AsyncClient, session: AsyncSession, kb: None, status: ElderStatus | None
) -> None:
    # The KB holds no personal data: unknown callers and callers not yet consented may ask.
    if status is not None:
        await add_elder(session, status=status)
    token = await start_call(client)

    response = await search(client, token, "số cấp cứu")

    assert response.status_code == 200
    assert response.json()["found"] is True


async def test_expired_or_unknown_token_is_rejected(
    client: AsyncClient, session: AsyncSession, kb: None
) -> None:
    token = await start_call(client)
    await session.execute(
        update(CallSession).values(expires_at=datetime.now(UTC) - timedelta(seconds=1))
    )

    for candidate in (token, "made-up-token"):
        response = await search(client, candidate, "số cấp cứu")
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "invalid_session"


@pytest.mark.parametrize(
    "body",
    [{"session_token": "t"}, {"session_token": "t", "query": ""}, {"query": "số cấp cứu"}],
)
async def test_missing_fields_are_a_validation_error(
    client: AsyncClient, body: dict[str, str]
) -> None:
    response = await client.post("/tools/search-knowledge", json=body, headers=DOGRAH_HEADERS)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


async def test_tool_requires_the_api_key(client: AsyncClient, kb: None) -> None:
    token = await start_call(client)

    response = await search(client, token, "số cấp cứu", headers={})

    assert response.status_code == 401
