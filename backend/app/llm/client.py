"""Gemini behind a small interface, so services can be tested with a fake (`tests/fakes.py`).

Every structured output is validated with its Pydantic schema before anyone uses it
(architecture invariant 6). Errors never carry prompt or transcript text.
"""

from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from functools import lru_cache
from typing import Literal, Protocol, TypeVar

import httpx
from google import genai
from google.genai import errors, types
from pydantic import BaseModel, ValidationError

from app.core.config import get_settings
from app.llm.embeddings import EMBEDDING_DIMS

SchemaT = TypeVar("SchemaT", bound=BaseModel)
EmbedTask = Literal["document", "query"]

_TASK_TYPES: dict[EmbedTask, str] = {"document": "RETRIEVAL_DOCUMENT", "query": "RETRIEVAL_QUERY"}
# Gemini's batchEmbedContents accepts at most 100 texts per request.
_EMBED_BATCH = 100


class LLMError(Exception):
    """The model call failed, or its output didn't match the schema."""


class LLMRateLimitedError(LLMError):
    """Quota or rate limit reached (HTTP 429): retry later, the input isn't at fault."""


class LLMNotConfiguredError(LLMError):
    """GEMINI_API_KEY is not set."""


class LLMClient(Protocol):
    async def generate_json(
        self, prompt: str, schema: type[SchemaT], *, system: str | None = None
    ) -> SchemaT:
        """Generate JSON matching `schema` and return it parsed."""
        ...

    async def embed(self, texts: Sequence[str], *, task: EmbedTask) -> list[list[float]]:
        """One `EMBEDDING_DIMS`-long vector per text, in order."""
        ...


class GeminiClient:
    def __init__(
        self,
        api_key: str,
        model: str,
        embedding_model: str,
        timeout_seconds: float,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._model = model
        self._embedding_model = embedding_model
        self._client: genai.Client | None = None
        if api_key:
            http_options = types.HttpOptions(
                timeout=int(timeout_seconds * 1000),
                async_client_args={"transport": transport} if transport else None,
            )
            self._client = genai.Client(api_key=api_key, http_options=http_options)

    async def generate_json(
        self, prompt: str, schema: type[SchemaT], *, system: str | None = None
    ) -> SchemaT:
        config = types.GenerateContentConfig(
            system_instruction=system,
            response_mime_type="application/json",
            response_json_schema=schema.model_json_schema(),
            temperature=0.2,
        )
        with _translate_errors():
            response = await self._api().aio.models.generate_content(
                model=self._model, contents=prompt, config=config
            )
        try:
            return schema.model_validate_json(response.text or "")
        except ValidationError as exc:
            raise LLMError(f"output does not match {schema.__name__}") from exc

    async def embed(self, texts: Sequence[str], *, task: EmbedTask) -> list[list[float]]:
        config = types.EmbedContentConfig(
            task_type=_TASK_TYPES[task], output_dimensionality=EMBEDDING_DIMS
        )
        vectors: list[list[float]] = []
        for start in range(0, len(texts), _EMBED_BATCH):
            batch = list(texts[start : start + _EMBED_BATCH])
            with _translate_errors():
                response = await self._api().aio.models.embed_content(
                    model=self._embedding_model, contents=batch, config=config
                )
            vectors += [embedding.values or [] for embedding in response.embeddings or []]
        if len(vectors) != len(texts) or any(len(v) != EMBEDDING_DIMS for v in vectors):
            raise LLMError("unexpected embedding response shape")
        return vectors

    def _api(self) -> genai.Client:
        if self._client is None:
            raise LLMNotConfiguredError("GEMINI_API_KEY is not set")
        return self._client


@contextmanager
def _translate_errors() -> Iterator[None]:
    try:
        yield
    except errors.APIError as exc:
        if exc.code == 429:
            raise LLMRateLimitedError("Gemini rate limit") from exc
        raise LLMError(f"Gemini API error {exc.code}") from exc
    except (httpx.HTTPError, TimeoutError) as exc:
        raise LLMError(f"Gemini request failed: {type(exc).__name__}") from exc


@lru_cache
def get_llm_client() -> LLMClient:
    settings = get_settings()
    return GeminiClient(
        settings.gemini_api_key,
        settings.gemini_model,
        settings.gemini_embedding_model,
        settings.llm_timeout_seconds,
    )
