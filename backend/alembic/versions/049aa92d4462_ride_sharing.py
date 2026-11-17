"""ride sharing

Revision ID: 049aa92d4462
Revises: 092895d242f7
Create Date: 2026-11-16 22:38:06.955284

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "049aa92d4462"
down_revision: str | Sequence[str] | None = "092895d242f7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "ride_notifications",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("booking_id", sa.Uuid(), nullable=False),
        sa.Column(
            "event",
            sa.Enum(
                "booked",
                "on_the_way",
                "arrived",
                "cancelled",
                name="event",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum(
                "pending",
                "sent",
                "failed",
                "skipped",
                name="status",
                native_enum=False,
                create_constraint=True,
            ),
            server_default="pending",
            nullable=False,
        ),
        sa.Column("attempts", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
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
            ["booking_id"],
            ["ride_bookings.id"],
            name=op.f("fk_ride_notifications_booking_id_ride_bookings"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ride_notifications")),
        sa.UniqueConstraint("booking_id", "event", name="uq_ride_notifications_booking_id_event"),
    )
    # The CHECK is created explicitly: add_column doesn't create an Enum's constraint.
    op.add_column(
        "elders",
        sa.Column(
            "ride_share_scope",
            sa.Enum("none", "status", "details", name="ride_share_scope", native_enum=False),
            nullable=True,
        ),
    )
    op.create_check_constraint(
        op.f("ck_elders_ride_share_scope"),
        "elders",
        "ride_share_scope IN ('none', 'status', 'details')",
    )
    op.add_column("elders", sa.Column("ride_share_decided_at", sa.DateTime(timezone=True)))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("elders", "ride_share_decided_at")
    op.drop_constraint(op.f("ck_elders_ride_share_scope"), "elders", type_="check")
    op.drop_column("elders", "ride_share_scope")
    op.drop_table("ride_notifications")
