"""scam patterns

Revision ID: 4b3ed2a15c4a
Revises: 29dd51ed62b1
Create Date: 2026-11-09 17:17:21.167311

"""

from collections.abc import Sequence

import pgvector.sqlalchemy
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "4b3ed2a15c4a"
down_revision: str | Sequence[str] | None = "29dd51ed62b1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # immutable_unaccent() comes from the knowledge-base migration (29dd51ed62b1).
    op.create_table(
        "scam_patterns",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "scam_type",
            sa.Enum(
                "police_impersonation",
                "bank_impersonation",
                "relative_impersonation",
                "investment",
                "health_product",
                "resort_contract",
                "fake_charity",
                "other",
                name="scam_type",
                native_enum=False,
                create_constraint=True,
                length=40,
            ),
            nullable=False,
        ),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("source", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column(
            "search_text",
            postgresql.TSVECTOR(),
            sa.Computed(
                "to_tsvector('simple', immutable_unaccent(title || ' ' || content))",
                persisted=True,
            ),
            nullable=False,
        ),
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
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_scam_patterns_created_by_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_scam_patterns")),
        sa.UniqueConstraint("title", name=op.f("uq_scam_patterns_title")),
    )
    op.create_index(
        "ix_scam_patterns_embedding",
        "scam_patterns",
        ["embedding"],
        unique=False,
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )
    op.create_index(
        "ix_scam_patterns_search_text",
        "scam_patterns",
        ["search_text"],
        unique=False,
        postgresql_using="gin",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_scam_patterns_search_text", table_name="scam_patterns")
    op.drop_index("ix_scam_patterns_embedding", table_name="scam_patterns")
    op.drop_table("scam_patterns")
