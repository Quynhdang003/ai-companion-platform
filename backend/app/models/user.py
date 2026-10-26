import uuid
from enum import StrEnum

from sqlalchemy import Enum, Text, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class UserRole(StrEnum):
    FAMILY = "family"
    ADMIN = "admin"


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    clerk_user_id: Mapped[str] = mapped_column(Text, unique=True)
    role: Mapped[UserRole] = mapped_column(
        Enum(
            UserRole,
            name="role",
            native_enum=False,
            create_constraint=True,
            values_callable=lambda e: [m.value for m in e],
        ),
        server_default=UserRole.FAMILY.value,
    )
