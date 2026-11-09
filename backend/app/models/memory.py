import uuid
from datetime import datetime
from enum import StrEnum

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    Text,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.llm.embeddings import EMBEDDING_DIMS
from app.models.base import Base, TimestampMixin


class MemoryCategory(StrEnum):
    PERSON = "person"
    PLACE = "place"
    HEALTH = "health"
    PREFERENCE = "preference"
    ROUTINE = "routine"
    EVENT = "event"


class Memory(TimestampMixin, Base):
    """A durable fact about an elder, extracted from their calls.

    Read only by backend jobs and the AI (pre-call hook, tools): web routes never return it.
    """

    __tablename__ = "memories"
    __table_args__ = (
        CheckConstraint("importance BETWEEN 1 AND 5", name="importance_range"),
        Index("ix_memories_elder_id_category", "elder_id", "category"),
        Index(
            "ix_memories_embedding",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    elder_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("elders.id", ondelete="CASCADE"))
    category: Mapped[MemoryCategory] = mapped_column(
        Enum(
            MemoryCategory,
            name="category",
            native_enum=False,
            create_constraint=True,
            values_callable=lambda e: [m.value for m in e],
        )
    )
    # Short name of the person, place or thing ("con gái Mai", "Bệnh viện Bạch Mai").
    subject: Mapped[str | None] = mapped_column(Text)
    # One short Vietnamese sentence about the elder.
    content: Mapped[str] = mapped_column(Text)
    # 1 (minor preference) .. 5 (health, safety, close family).
    importance: Mapped[int] = mapped_column(SmallInteger)
    # Calls that added or confirmed this memory.
    mention_count: Mapped[int] = mapped_column(Integer, server_default=text("1"))
    last_mentioned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    # The call it was last extracted from (audit; kept if that log is deleted).
    source_call_log_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("call_logs.id", ondelete="SET NULL")
    )
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIMS))
