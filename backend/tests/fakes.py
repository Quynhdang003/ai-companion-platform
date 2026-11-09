"""Test doubles for external services."""

import hashlib
import math
import random
from collections.abc import Sequence

from pydantic import BaseModel, ValidationError

from app.llm.client import EmbedTask, LLMError, SchemaT
from app.llm.embeddings import EMBEDDING_DIMS


def fake_vector(text: str) -> list[float]:
    """Deterministic unit vector: the same text always gets the same embedding."""
    rng = random.Random(hashlib.sha256(text.encode("utf-8")).digest())
    values = [rng.uniform(-1.0, 1.0) for _ in range(EMBEDDING_DIMS)]
    norm = math.sqrt(sum(v * v for v in values))
    return [v / norm for v in values]


class FakeLLMClient:
    """`LLMClient` that replays queued replies.

    Queue JSON strings, dicts / Pydantic models (serialized as the model's reply) or exceptions
    (raised) in `replies`; set `embed_error` to make `embed` fail.
    """

    def __init__(self) -> None:
        self.replies: list[str | dict[str, object] | BaseModel | Exception] = []
        self.prompts: list[str] = []
        self.embedded: list[tuple[list[str], EmbedTask]] = []
        self.embed_error: Exception | None = None

    async def generate_json(
        self, prompt: str, schema: type[SchemaT], *, system: str | None = None
    ) -> SchemaT:
        self.prompts.append(prompt)
        if not self.replies:
            raise AssertionError("FakeLLMClient: no reply queued")
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        if isinstance(reply, BaseModel):
            reply = reply.model_dump_json()
        try:
            if isinstance(reply, dict):
                return schema.model_validate(reply)
            return schema.model_validate_json(reply)
        except ValidationError as exc:
            raise LLMError(f"output does not match {schema.__name__}") from exc

    async def embed(self, texts: Sequence[str], *, task: EmbedTask) -> list[list[float]]:
        if self.embed_error is not None:
            raise self.embed_error
        self.embedded.append((list(texts), task))
        return [fake_vector(text) for text in texts]
