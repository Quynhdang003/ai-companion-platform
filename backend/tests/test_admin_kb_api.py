"""Admin KB routes: /api/admin/kb/documents. Admins only; saved documents are searchable at once."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from httpx import AsyncClient, Response
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.llm.client import LLMError, LLMNotConfiguredError, LLMRateLimitedError, get_llm_client
from app.main import app
from app.models import KbChunk, KbDocument, User, UserRole
from app.schemas.kb import CONTENT_MAX, TITLE_MAX
from app.services.rag import documents, ingest
from app.services.rag.ingest import add_document
from tests.conftest import DOGRAH_HEADERS, HeadersFactory, start_call
from tests.fakes import FakeLLMClient

URL = "/api/admin/kb/documents"
HOTLINES = "Số tổng đài chính thức"
HOTLINES_TEXT = (
    "Tổng đài Viettel Post: 1900 8095. Tổng đài Vietcombank: 1900 545413. "
    "Nhân viên thật không bao giờ hỏi mã OTP."
)
EMERGENCY = "Số điện thoại khẩn cấp"
EMERGENCY_TEXT = "Gọi 113 khi cần công an. Gọi 115 khi cần xe cấp cứu."


@pytest.fixture
def llm(client: AsyncClient) -> FakeLLMClient:
    """The LLM client the routes use (after `client` set its own)."""
    fake = FakeLLMClient()
    app.dependency_overrides[get_llm_client] = lambda: fake
    return fake


@pytest.fixture
async def admin(session: AsyncSession) -> User:
    user = User(clerk_user_id="user_admin", role=UserRole.ADMIN)
    session.add(user)
    await session.flush()
    return user


@pytest.fixture
def headers(admin: User, auth_headers: HeadersFactory) -> dict[str, str]:
    return auth_headers(admin.clerk_user_id)


async def create(
    client: AsyncClient, headers: dict[str, str], title: str = HOTLINES, **fields: Any
) -> Response:
    body = {"title": title, "content": HOTLINES_TEXT, **fields}
    return await client.post(URL, json=body, headers=headers)


async def chunks(session: AsyncSession, document_id: str) -> list[str]:
    stmt = (
        select(KbChunk.content)
        .where(KbChunk.document_id == uuid.UUID(document_id))
        .order_by(KbChunk.chunk_index)
    )
    return list((await session.scalars(stmt)).all())


async def ask(client: AsyncClient, query: str) -> dict[str, Any]:
    """What `search_knowledge` answers in a live call (any caller may search the KB)."""
    token = await start_call(client, from_number="0987654321")
    response = await client.post(
        "/tools/search-knowledge",
        json={"session_token": token, "query": query},
        headers=DOGRAH_HEADERS,
    )
    assert response.status_code == 200
    return response.json()


# Who may


async def test_family_users_and_signed_out_callers_are_refused(
    client: AsyncClient, llm: FakeLLMClient, auth_headers: HeadersFactory
) -> None:
    family = auth_headers("user_family")
    doc = f"{URL}/{uuid.uuid4()}"
    body = {"title": HOTLINES, "content": HOTLINES_TEXT}
    calls = [
        client.get(URL, headers=family),
        client.get(doc, headers=family),
        client.post(URL, json=body, headers=family),
        client.put(doc, json=body, headers=family),
        client.delete(doc, headers=family),
    ]
    for call in calls:
        response = await call
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "forbidden"

    assert (await client.get(URL)).status_code == 401
    assert (await client.post(URL, json=body)).status_code == 401
    assert llm.embedded == []


# Adding


async def test_added_document_is_indexed_and_answers_calls_at_once(
    client: AsyncClient,
    session: AsyncSession,
    llm: FakeLLMClient,
    admin: User,
    headers: dict[str, str],
) -> None:
    response = await create(client, headers, source="  hotlines.md ")

    assert response.status_code == 201
    body = response.json()
    assert set(body) == {
        "id",
        "title",
        "source",
        "content",
        "chunk_count",
        "created_at",
        "updated_at",
    }
    assert (body["title"], body["source"], body["content"]) == (
        HOTLINES,
        "hotlines.md",
        HOTLINES_TEXT,
    )
    assert body["chunk_count"] == 1
    assert await chunks(session, body["id"]) == [HOTLINES_TEXT]
    [(texts, task)] = llm.embedded
    assert (texts, task) == ([f"{HOTLINES}\n{HOTLINES_TEXT}"], "document")
    document = await session.get(KbDocument, uuid.UUID(body["id"]))
    assert document is not None and document.created_by == admin.id

    answer = await ask(client, "số tổng đài Viettel Post là bao nhiêu")
    assert answer["found"] is True
    assert answer["results"][0] == {"title": HOTLINES, "content": HOTLINES_TEXT}


async def test_text_is_trimmed_and_a_blank_source_is_none(
    client: AsyncClient, llm: FakeLLMClient, headers: dict[str, str]
) -> None:
    response = await client.post(
        URL,
        json={"title": f"  {HOTLINES}\n", "content": f"\n{HOTLINES_TEXT}  ", "source": "  "},
        headers=headers,
    )

    assert response.status_code == 201
    body = response.json()
    assert (body["title"], body["content"], body["source"]) == (HOTLINES, HOTLINES_TEXT, None)


@pytest.mark.parametrize(
    "fields",
    [
        {"title": "  "},
        {"title": "x" * (TITLE_MAX + 1)},
        {"content": " \n "},
        {"content": "x" * (CONTENT_MAX + 1)},
        {"source": "x" * 501},
        {"content": None},
    ],
)
async def test_invalid_bodies_are_refused_before_embedding(
    client: AsyncClient, llm: FakeLLMClient, headers: dict[str, str], fields: dict[str, Any]
) -> None:
    response = await create(client, headers, **fields)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
    assert llm.embedded == []


async def test_text_the_chunker_finds_nothing_in_is_an_empty_document(
    client: AsyncClient,
    llm: FakeLLMClient,
    headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Any non-blank text makes a chunk today; the route still maps the service's error.
    monkeypatch.setattr(ingest, "chunk_text", lambda _: [])

    response = await create(client, headers)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "empty_document"
    assert llm.embedded == []


async def test_taken_title_is_refused_before_embedding(
    client: AsyncClient, session: AsyncSession, llm: FakeLLMClient, headers: dict[str, str]
) -> None:
    await create(client, headers)

    response = await create(client, headers, content="Một nội dung khác.")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "title_taken"
    assert len(llm.embedded) == 1
    assert await session.scalar(select(func.count()).select_from(KbDocument)) == 1


async def test_title_saved_meanwhile_is_refused_too(
    client: AsyncClient,
    session: AsyncSession,
    llm: FakeLLMClient,
    headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await create(client, headers)

    async def free(*_: Any, **__: Any) -> None:  # another request passed the check first
        return None

    monkeypatch.setattr(documents, "_check_title_free", free)
    response = await create(client, headers, content="Một nội dung khác.")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "title_taken"
    # The session is still usable: the failed insert was rolled back to its savepoint.
    assert [d["title"] for d in (await client.get(URL, headers=headers)).json()] == [HOTLINES]


@pytest.mark.parametrize(
    ("error", "status", "code"),
    [
        (LLMError("down"), 503, "embedding_unavailable"),
        (LLMRateLimitedError("quota"), 503, "embedding_unavailable"),
        (LLMNotConfiguredError("no key"), 500, "llm_not_configured"),
    ],
)
async def test_embedding_failure_stores_nothing(
    client: AsyncClient,
    session: AsyncSession,
    llm: FakeLLMClient,
    headers: dict[str, str],
    error: Exception,
    status: int,
    code: str,
) -> None:
    llm.embed_error = error

    response = await create(client, headers)

    assert response.status_code == status
    assert response.json()["error"]["code"] == code
    assert await session.scalar(select(func.count()).select_from(KbDocument)) == 0
    assert await session.scalar(select(func.count()).select_from(KbChunk)) == 0


# Listing and reading


async def test_list_is_newest_first_with_chunk_counts_and_accent_free_title_search(
    client: AsyncClient, session: AsyncSession, headers: dict[str, str]
) -> None:
    fake = FakeLLMClient()
    older = await add_document(session, fake, title=EMERGENCY, content=EMERGENCY_TEXT)
    long_text = " ".join(f"Câu thứ {i} nói về an toàn khi nghe điện thoại lạ." for i in range(60))
    newer = await add_document(session, fake, title="An toàn 100%", content=long_text)
    await session.execute(
        update(KbDocument)
        .where(KbDocument.id == older.id)
        .values(updated_at=datetime.now(UTC) - timedelta(days=1))
    )

    response = await client.get(URL, headers=headers)

    assert response.status_code == 200
    listed = response.json()
    assert [d["title"] for d in listed] == ["An toàn 100%", EMERGENCY]
    assert set(listed[0]) == {"id", "title", "source", "chunk_count", "created_at", "updated_at"}
    assert listed[0]["chunk_count"] > 1
    assert listed[1]["chunk_count"] == 1
    assert listed[0]["id"] == str(newer.id)

    async def titles(q: str) -> list[str]:
        found = await client.get(URL, params={"q": q}, headers=headers)
        return [d["title"] for d in found.json()]

    assert await titles("so DIEN thoai khan") == [EMERGENCY]
    assert await titles("điện thoại") == [EMERGENCY]
    assert await titles("100%") == ["An toàn 100%"]
    assert await titles("%") == ["An toàn 100%"]  # a literal percent sign, not a wildcard
    assert await titles("_") == []
    assert await titles("  ") == ["An toàn 100%", EMERGENCY]


async def test_document_is_read_whole_and_unknown_ids_are_not_found(
    client: AsyncClient, session: AsyncSession, headers: dict[str, str]
) -> None:
    document = await add_document(
        session, FakeLLMClient(), title=EMERGENCY, content=EMERGENCY_TEXT, source="seed"
    )

    response = await client.get(f"{URL}/{document.id}", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert (body["title"], body["content"], body["source"], body["chunk_count"]) == (
        EMERGENCY,
        EMERGENCY_TEXT,
        "seed",
        1,
    )
    missing = await client.get(f"{URL}/{uuid.uuid4()}", headers=headers)
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "not_found"
    assert (await client.get(f"{URL}/not-a-uuid", headers=headers)).status_code == 422


# Editing


async def test_edit_replaces_the_chunks_and_calls_find_the_new_text(
    client: AsyncClient, session: AsyncSession, llm: FakeLLMClient, headers: dict[str, str]
) -> None:
    created = (await create(client, headers)).json()
    new_text = "Tổng đài Viettel Post mới: 1900 8095 bấm phím 1. Không ai hỏi mã OTP."

    response = await client.put(
        f"{URL}/{created['id']}",
        json={"title": "Tổng đài chính thức", "content": new_text, "source": "v2"},
        headers=headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert (body["id"], body["title"], body["content"], body["source"]) == (
        created["id"],
        "Tổng đài chính thức",
        new_text,
        "v2",
    )
    assert await chunks(session, created["id"]) == [new_text]
    assert llm.embedded[-1] == ([f"Tổng đài chính thức\n{new_text}"], "document")
    answer = await ask(client, "tổng đài Viettel Post bấm phím mấy")
    assert answer["results"][0]["title"] == "Tổng đài chính thức"
    assert "Vietcombank" not in str(answer)


async def test_new_source_alone_costs_no_embedding(
    client: AsyncClient, llm: FakeLLMClient, headers: dict[str, str]
) -> None:
    created = (await create(client, headers)).json()

    response = await client.put(
        f"{URL}/{created['id']}",
        json={"title": HOTLINES, "content": HOTLINES_TEXT, "source": "hotlines-v2.md"},
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()["source"] == "hotlines-v2.md"
    assert len(llm.embedded) == 1


async def test_edit_to_another_documents_title_is_refused(
    client: AsyncClient, llm: FakeLLMClient, headers: dict[str, str]
) -> None:
    await create(client, headers, title=EMERGENCY)
    created = (await create(client, headers)).json()

    response = await client.put(
        f"{URL}/{created['id']}",
        json={"title": EMERGENCY, "content": HOTLINES_TEXT},
        headers=headers,
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "title_taken"
    assert len(llm.embedded) == 2


async def test_failed_edit_keeps_the_stored_version(
    client: AsyncClient, session: AsyncSession, llm: FakeLLMClient, headers: dict[str, str]
) -> None:
    created = (await create(client, headers)).json()
    llm.embed_error = LLMError("down")

    response = await client.put(
        f"{URL}/{created['id']}",
        json={"title": "Tiêu đề mới", "content": "Nội dung mới."},
        headers=headers,
    )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "embedding_unavailable"
    kept = (await client.get(f"{URL}/{created['id']}", headers=headers)).json()
    assert (kept["title"], kept["content"]) == (HOTLINES, HOTLINES_TEXT)
    assert await chunks(session, created["id"]) == [HOTLINES_TEXT]


async def test_editing_an_unknown_document_is_not_found(
    client: AsyncClient, llm: FakeLLMClient, headers: dict[str, str]
) -> None:
    response = await client.put(
        f"{URL}/{uuid.uuid4()}", json={"title": HOTLINES, "content": HOTLINES_TEXT}, headers=headers
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"
    assert llm.embedded == []


# Deleting


async def test_deleted_document_and_its_chunks_are_gone(
    client: AsyncClient, session: AsyncSession, llm: FakeLLMClient, headers: dict[str, str]
) -> None:
    created = (await create(client, headers)).json()

    response = await client.delete(f"{URL}/{created['id']}", headers=headers)

    assert response.status_code == 204
    assert response.content == b""
    assert await session.scalar(select(func.count()).select_from(KbChunk)) == 0
    assert (await ask(client, "số tổng đài Viettel Post"))["found"] is False
    again = await client.delete(f"{URL}/{created['id']}", headers=headers)
    assert again.status_code == 404
    assert again.json()["error"]["code"] == "not_found"
