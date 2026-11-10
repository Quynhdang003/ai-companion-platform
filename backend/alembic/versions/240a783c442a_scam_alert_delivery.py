"""scam alert delivery

Revision ID: 240a783c442a
Revises: 80d72daa5d7d
Create Date: 2026-11-10 17:10:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "240a783c442a"
down_revision: str | Sequence[str] | None = "80d72daa5d7d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CHECK = "ck_scam_events_alert_status"


def _alert_status_check(*values: str) -> None:
    allowed = ", ".join(f"'{value}'" for value in values)
    # op.f: the full name, not the `constraint_name` token of the naming convention.
    op.drop_constraint(op.f(CHECK), "scam_events", type_="check")
    op.create_check_constraint(op.f(CHECK), "scam_events", f"alert_status IN ({allowed})")


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "scam_events",
        sa.Column("alert_attempts", sa.Integer(), server_default=sa.text("0"), nullable=False),
    )
    op.add_column("scam_events", sa.Column("alerted_at", sa.DateTime(timezone=True)))
    # `skipped`: nobody to alert (no family member connected Telegram, or too late).
    _alert_status_check("pending", "sent", "failed", "skipped")


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("UPDATE scam_events SET alert_status = 'failed' WHERE alert_status = 'skipped'")
    _alert_status_check("pending", "sent", "failed")
    op.drop_column("scam_events", "alerted_at")
    op.drop_column("scam_events", "alert_attempts")
