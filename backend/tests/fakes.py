"""Test doubles for external services."""

import asyncio
import hashlib
import math
import random
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

from pydantic import BaseModel, ValidationError

from app.llm.client import EmbedTask, LLMError, SchemaT
from app.llm.embeddings import EMBEDDING_DIMS
from app.models import RideStatus, RideType
from app.services.notification.telegram import TelegramUpdate
from app.services.ride.provider import (
    GeoPoint,
    ProviderBooking,
    ProviderPlace,
    ProviderQuote,
)


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


class QueryVectorLLM(FakeLLMClient):
    """Embeds every query as `query_as`, to exercise a vector ranking alone."""

    def __init__(self, query_as: str) -> None:
        super().__init__()
        self.query_as = query_as

    async def embed(self, texts: Sequence[str], *, task: EmbedTask) -> list[list[float]]:
        if task == "query":
            return [fake_vector(self.query_as) for _ in texts]
        return await super().embed(texts, task=task)


class SlowLLM(FakeLLMClient):
    """Query embeddings take a second, longer than the search timeouts used in tests."""

    async def embed(self, texts: Sequence[str], *, task: EmbedTask) -> list[list[float]]:
        if task == "query":
            await asyncio.sleep(1)
        return await super().embed(texts, task=task)


class FakeTelegramBot:
    """`TelegramApi` that records sent messages and replays queued updates.

    Queue lists of updates (one per `get_updates` call) or exceptions in `updates`; put an
    exception in `send_errors[chat_id]` to make sending to that chat fail.
    """

    def __init__(self) -> None:
        self.updates: list[list[TelegramUpdate] | Exception] = []
        self.offsets: list[int | None] = []
        self.sent: list[tuple[str, str]] = []
        self.send_errors: dict[str, Exception] = {}

    async def send(self, recipient: str, text: str) -> None:
        if recipient in self.send_errors:
            raise self.send_errors[recipient]
        self.sent.append((recipient, text))

    async def get_updates(self, offset: int | None) -> list[TelegramUpdate]:
        self.offsets.append(offset)
        batch = self.updates.pop(0) if self.updates else []
        if isinstance(batch, Exception):
            raise batch
        return batch


def private_message(update_id: int, chat_id: int, text: str) -> TelegramUpdate:
    return TelegramUpdate.model_validate(
        {
            "update_id": update_id,
            "message": {"chat": {"id": chat_id, "type": "private"}, "text": text},
        }
    )


class FakeRideProvider:
    """`RideProvider` in memory, recording every call.

    `places` answer any search; `pickup_eta_s = None` means no driver near; set `surge`.
    Put an exception in `errors["search_places" | "quote" | "book"]` to make that call
    fail (remove it to let it work again). A quote is booked once: booking it again returns
    the same booking, like the simulator.
    """

    TRIP_S = 799
    DISTANCE_M = 4_132

    def __init__(self) -> None:
        self.places: list[ProviderPlace] = []
        self.price_vnd = 72_000
        self.pickup_eta_s: int | None = 283
        self.surge = False
        self.errors: dict[str, Exception] = {}
        self.searches: list[tuple[str, int]] = []
        self.quotes: list[tuple[RideType, GeoPoint, GeoPoint]] = []
        self.booked: list[str] = []
        self._bookings: dict[str, ProviderBooking] = {}

    def _maybe_fail(self, method: str) -> None:
        if method in self.errors:
            raise self.errors[method]

    async def search_places(self, query: str, limit: int) -> list[ProviderPlace]:
        self.searches.append((query, limit))
        self._maybe_fail("search_places")
        return self.places[:limit]

    async def quote(
        self, ride_type: RideType, pickup: GeoPoint, destination: GeoPoint
    ) -> ProviderQuote:
        self.quotes.append((ride_type, pickup, destination))
        self._maybe_fail("quote")
        return ProviderQuote(
            id=f"quote-{uuid.uuid4().hex[:8]}",
            ride_type=ride_type,
            price_vnd=self.price_vnd,
            distance_m=self.DISTANCE_M,
            duration_s=self.TRIP_S,
            pickup_eta_s=self.pickup_eta_s,
            surge=self.surge,
            expires_at=datetime.now(UTC) + timedelta(minutes=5),
        )

    async def book(self, quote_id: str) -> ProviderBooking:
        self.booked.append(quote_id)
        self._maybe_fail("book")
        if quote_id not in self._bookings:
            eta = self.pickup_eta_s
            self._bookings[quote_id] = ProviderBooking(
                id=f"booking-{uuid.uuid4().hex[:8]}",
                quote_id=quote_id,
                status=RideStatus.REQUESTED,
                driver=None,
                pickup_eta_s=eta,
                dropoff_eta_s=None if eta is None else eta + self.TRIP_S,
            )
        return self._bookings[quote_id]
