"""ride status sync

Revision ID: 092895d242f7
Revises: 2743a0704e49
Create Date: 2026-11-16 22:24:07.303420

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "092895d242f7"
down_revision: str | Sequence[str] | None = "2743a0704e49"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # The CHECK is created explicitly: add_column doesn't create an Enum's constraint.
    op.add_column(
        "ride_bookings",
        sa.Column(
            "cancel_reason",
            sa.Enum("rider", "driver", "lost", name="cancel_reason", native_enum=False),
            nullable=True,
        ),
    )
    op.create_check_constraint(
        op.f("ck_ride_bookings_cancel_reason"),
        "ride_bookings",
        "cancel_reason IN ('rider', 'driver', 'lost')",
    )
    op.add_column("ride_bookings", sa.Column("synced_at", sa.DateTime(timezone=True)))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("ride_bookings", "synced_at")
    op.drop_constraint(op.f("ck_ride_bookings_cancel_reason"), "ride_bookings", type_="check")
    op.drop_column("ride_bookings", "cancel_reason")
