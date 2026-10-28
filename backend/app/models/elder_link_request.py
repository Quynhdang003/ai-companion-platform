import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Uuid, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class LinkRequestStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class ElderLinkRequest(Base):
    """A family member asking an elder's owner to be linked (registered a taken number)."""

    __tablename__ = "elder_link_requests"
    __table_args__ = (
        # At most one open request per requester and elder; decided ones are kept as history.
        Index(
            "uq_elder_link_requests_pending",
            "elder_id",
            "requester_id",
            unique=True,
            postgresql_where=text("status = 'pending'"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    elder_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("elders.id", ondelete="CASCADE"), index=True
    )
    requester_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[LinkRequestStatus] = mapped_column(
        Enum(
            LinkRequestStatus,
            name="status",
            native_enum=False,
            create_constraint=True,
            values_callable=lambda e: [m.value for m in e],
        ),
        server_default=LinkRequestStatus.PENDING.value,
    )
    decided_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
