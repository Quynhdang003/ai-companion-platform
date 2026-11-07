"""memories

Revision ID: 45022702e0a4
Revises: 87d572f79894
Create Date: 2026-11-07 17:58:56.714801

"""

from collections.abc import Sequence

import pgvector.sqlalchemy
import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "45022702e0a4"
down_revision: str | Sequence[str] | None = "87d572f79894"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "memories",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("elder_id", sa.Uuid(), nullable=False),
        sa.Column(
            "category",
            sa.Enum(
                "person",
                "place",
                "health",
                "preference",
                "routine",
                "event",
                name="category",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("subject", sa.Text(), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("importance", sa.SmallInteger(), nullable=False),
        sa.Column("mention_count", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column(
            "last_mentioned_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("source_call_log_id", sa.Uuid(), nullable=True),
        sa.Column("embedding", pgvector.sqlalchemy.vector.VECTOR(dim=768), nullable=False),
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
        sa.CheckConstraint("importance BETWEEN 1 AND 5", name=op.f("ck_memories_importance_range")),
        sa.ForeignKeyConstraint(
            ["elder_id"],
            ["elders.id"],
            name=op.f("fk_memories_elder_id_elders"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["source_call_log_id"],
            ["call_logs.id"],
            name=op.f("fk_memories_source_call_log_id_call_logs"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_memories")),
    )
    op.create_index(
        "ix_memories_elder_id_category", "memories", ["elder_id", "category"], unique=False
    )
    op.create_index(
        "ix_memories_embedding",
        "memories",
        ["embedding"],
        unique=False,
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )
    op.add_column(
        "call_logs",
        sa.Column(
            "memory_status",
            sa.Enum(
                "pending",
                "done",
                "skipped",
                "failed",
                name="memory_status",
                native_enum=False,
                create_constraint=True,
            ),
            server_default="skipped",
            nullable=False,
        ),
    )
    op.add_column(
        "call_logs",
        sa.Column("memory_attempts", sa.Integer(), server_default=sa.text("0"), nullable=False),
    )
    # Transcripts stored before this migration get their memories extracted too.
    op.execute("UPDATE call_logs SET memory_status = 'pending' WHERE transcript IS NOT NULL")


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("call_logs", "memory_attempts")
    op.drop_column("call_logs", "memory_status")
    op.drop_index(
        "ix_memories_embedding",
        table_name="memories",
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )
    op.drop_index("ix_memories_elder_id_category", table_name="memories")
    op.drop_table("memories")
    op.execute("DROP EXTENSION IF EXISTS vector")
