"""knowledge base

Revision ID: 29dd51ed62b1
Revises: 45022702e0a4
Create Date: 2026-11-07 19:21:51.087633

"""

from collections.abc import Sequence

import pgvector.sqlalchemy
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "29dd51ed62b1"
down_revision: str | Sequence[str] | None = "45022702e0a4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("CREATE EXTENSION IF NOT EXISTS unaccent")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    # unaccent() is only STABLE (its dictionary could change), so generated columns and
    # indexes can't call it. Pinning the dictionary makes this wrapper safe to mark IMMUTABLE.
    op.execute(
        """
        CREATE FUNCTION immutable_unaccent(text) RETURNS text
        LANGUAGE sql IMMUTABLE PARALLEL SAFE STRICT
        AS $$ SELECT public.unaccent('public.unaccent'::regdictionary, $1) $$
        """
    )
    op.create_table(
        "kb_documents",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("source", sa.Text(), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_kb_documents_created_by_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_kb_documents")),
        sa.UniqueConstraint("title", name=op.f("uq_kb_documents_title")),
    )
    op.create_table(
        "kb_chunks",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "search_text",
            postgresql.TSVECTOR(),
            sa.Computed("to_tsvector('simple', immutable_unaccent(content))", persisted=True),
            nullable=False,
        ),
        sa.Column("embedding", pgvector.sqlalchemy.vector.VECTOR(dim=768), nullable=False),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["kb_documents.id"],
            name=op.f("fk_kb_chunks_document_id_kb_documents"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_kb_chunks")),
        sa.UniqueConstraint(
            "document_id", "chunk_index", name="uq_kb_chunks_document_id_chunk_index"
        ),
    )
    op.execute(
        "CREATE INDEX ix_kb_chunks_content_trgm ON kb_chunks "
        "USING gin (immutable_unaccent(lower(content)) gin_trgm_ops)"
    )
    op.create_index(
        "ix_kb_chunks_embedding",
        "kb_chunks",
        ["embedding"],
        unique=False,
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )
    op.create_index(
        "ix_kb_chunks_search_text",
        "kb_chunks",
        ["search_text"],
        unique=False,
        postgresql_using="gin",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_kb_chunks_search_text", table_name="kb_chunks")
    op.drop_index("ix_kb_chunks_embedding", table_name="kb_chunks")
    op.drop_index("ix_kb_chunks_content_trgm", table_name="kb_chunks")
    op.drop_table("kb_chunks")
    op.drop_table("kb_documents")
    op.execute("DROP FUNCTION IF EXISTS immutable_unaccent(text)")
    op.execute("DROP EXTENSION IF EXISTS pg_trgm")
    op.execute("DROP EXTENSION IF EXISTS unaccent")
