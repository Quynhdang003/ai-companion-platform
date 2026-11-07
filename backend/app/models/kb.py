import uuid

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Computed,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column

from app.llm.embeddings import EMBEDDING_DIMS
from app.models.base import Base, TimestampMixin


class KbDocument(TimestampMixin, Base):
    """Knowledge-base document (elderly support, the service, safety, scams), managed by admins.

    The full text is kept so the chunks can be rebuilt (re-chunking, re-embedding).
    """

    __tablename__ = "kb_documents"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    title: Mapped[str] = mapped_column(Text, unique=True)
    # Where it came from (file name, URL), for admins.
    source: Mapped[str | None] = mapped_column(Text)
    content: Mapped[str] = mapped_column(Text)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )


class KbChunk(Base):
    """A searchable piece of a document: full-text (`search_text`), trigram and vector indexes.

    `immutable_unaccent()` is a SQL function from the KB migration: `unaccent` itself isn't
    IMMUTABLE, so it can't be used in generated columns or indexes.
    """

    __tablename__ = "kb_chunks"
    __table_args__ = (
        UniqueConstraint("document_id", "chunk_index", name="uq_kb_chunks_document_id_chunk_index"),
        Index("ix_kb_chunks_search_text", "search_text", postgresql_using="gin"),
        Index(
            "ix_kb_chunks_content_trgm",
            func.immutable_unaccent(func.lower(text("content"))).label("content_unaccented"),
            postgresql_using="gin",
            postgresql_ops={"content_unaccented": "gin_trgm_ops"},
        ),
        Index(
            "ix_kb_chunks_embedding",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("kb_documents.id", ondelete="CASCADE")
    )
    chunk_index: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    # Accent-free tokens ("bệnh viện" -> "benh", "vien"): STT output and queries without
    # diacritics still match.
    search_text: Mapped[str] = mapped_column(
        TSVECTOR, Computed("to_tsvector('simple', immutable_unaccent(content))", persisted=True)
    )
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIMS))
