import json
from collections.abc import Callable

import httpx
import pytest
from pydantic import BaseModel

from app.core.config import get_settings
from app.llm.client import (
    GeminiClient,
    LLMError,
    LLMNotConfiguredError,
    LLMRateLimitedError,
    get_llm_client,
)
from app.llm.embeddings import EMBEDDING_DIMS
from tests.fakes import FakeLLMClient, fake_vector

Handler = Callable[[httpx.Request], httpx.Response]


class Answer(BaseModel):
    answer: str


def gemini(handler: Handler) -> GeminiClient:
    return GeminiClient(
        "test-key",
        "gemini-test",
        "gemini-embedding-001",
        timeout_seconds=5,
        transport=httpx.MockTransport(handler),
    )


def text_reply(text: str) -> httpx.Response:
    return httpx.Response(
        200, json={"candidates": [{"content": {"role": "model", "parts": [{"text": text}]}}]}
    )


def api_error(status: int) -> httpx.Response:
    return httpx.Response(
        status, json={"error": {"code": status, "message": "nope", "status": "ERROR"}}
    )


async def test_generate_json_asks_for_the_schema_and_parses_the_reply() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return text_reply('{"answer": "dạ"}')

    result = await gemini(handler).generate_json("Hỏi gì đó", Answer, system="Trả lời ngắn")

    assert result == Answer(answer="dạ")
    body = json.loads(requests[0].content)
    config = body["generationConfig"]
    assert config["responseMimeType"] == "application/json"
    assert config["responseJsonSchema"]["properties"]["answer"]["type"] == "string"
    assert "gemini-test:generateContent" in requests[0].url.path


@pytest.mark.parametrize("text", ['{"other": 1}', "not json", ""])
async def test_generate_json_rejects_output_outside_the_schema(text: str) -> None:
    with pytest.raises(LLMError, match="Answer"):
        await gemini(lambda _: text_reply(text)).generate_json("x", Answer)


async def test_rate_limit_is_its_own_error() -> None:
    with pytest.raises(LLMRateLimitedError):
        await gemini(lambda _: api_error(429)).generate_json("x", Answer)


@pytest.mark.parametrize("status", [400, 500])
async def test_other_api_errors_are_llm_errors(status: int) -> None:
    with pytest.raises(LLMError) as info:
        await gemini(lambda _: api_error(status)).generate_json("x", Answer)
    assert not isinstance(info.value, LLMRateLimitedError)


async def test_network_failure_is_an_llm_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down", request=request)

    with pytest.raises(LLMError, match="ConnectError"):
        await gemini(handler).generate_json("x", Answer)


async def test_embed_sends_task_and_dimensions_in_batches_of_100() -> None:
    requests: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        requests.append(body)
        return httpx.Response(
            200, json={"embeddings": [{"values": [0.1] * EMBEDDING_DIMS} for _ in body["requests"]]}
        )

    vectors = await gemini(handler).embed([f"câu {i}" for i in range(150)], task="query")

    assert len(vectors) == 150
    assert [len(r["requests"]) for r in requests] == [100, 50]
    first = requests[0]["requests"][0]
    assert first["taskType"] == "RETRIEVAL_QUERY"
    assert first["outputDimensionality"] == EMBEDDING_DIMS


async def test_embed_rejects_wrong_dimensions() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"embeddings": [{"values": [0.1, 0.2]}]})

    with pytest.raises(LLMError, match="shape"):
        await gemini(handler).embed(["một"], task="document")


async def test_missing_api_key_fails_on_use_not_on_startup() -> None:
    client = GeminiClient("", "gemini-test", "gemini-embedding-001", timeout_seconds=5)

    with pytest.raises(LLMNotConfiguredError):
        await client.generate_json("x", Answer)
    with pytest.raises(LLMNotConfiguredError):
        await client.embed(["x"], task="document")


async def test_fake_client_replays_replies_and_embeds_deterministically() -> None:
    fake = FakeLLMClient()
    fake.replies += [{"answer": "a"}, '{"wrong": 1}', LLMRateLimitedError("quota")]

    assert await fake.generate_json("p", Answer) == Answer(answer="a")
    with pytest.raises(LLMError):
        await fake.generate_json("p", Answer)
    with pytest.raises(LLMRateLimitedError):
        await fake.generate_json("p", Answer)
    vectors = await fake.embed(["a", "a", "b"], task="document")
    assert vectors[0] == vectors[1] != vectors[2]
    assert vectors[0] == fake_vector("a") and len(vectors[0]) == EMBEDDING_DIMS


@pytest.mark.live
async def test_live_gemini_json_and_embedding() -> None:
    """`uv run pytest -m live`: one real generate + one real embed request."""
    if not get_settings().gemini_api_key:
        pytest.skip("GEMINI_API_KEY is not set")
    client = get_llm_client()

    result = await client.generate_json(
        'Trả về JSON với "answer" là từ "xin chào" viết hoa chữ cái đầu.', Answer
    )
    vectors = await client.embed(["Bệnh viện Bạch Mai"], task="document")

    assert result.answer.strip()
    assert len(vectors) == 1 and len(vectors[0]) == EMBEDDING_DIMS
