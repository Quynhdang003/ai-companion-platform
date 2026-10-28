import uuid
from datetime import datetime
from typing import Annotated, Literal, Self

from pydantic import BaseModel, StringConstraints, field_validator

from app.models import Elder, ElderStatus, FamilyRole

FullName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
PreferredName = Annotated[str, StringConstraints(strip_whitespace=True, max_length=50)]
RawPhone = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=32)]


class ElderCreate(BaseModel):
    full_name: FullName
    # Normalized to E.164 by the route.
    phone: RawPhone
    preferred_name: PreferredName | None = None

    @field_validator("preferred_name")
    @classmethod
    def _blank_to_none(cls, value: str | None) -> str | None:
        return value or None


class ElderOut(BaseModel):
    id: uuid.UUID
    full_name: str
    preferred_name: str | None
    phone_e164: str
    status: ElderStatus
    my_role: FamilyRole
    created_at: datetime

    @classmethod
    def from_link(cls, elder: Elder, role: FamilyRole) -> Self:
        return cls(
            id=elder.id,
            full_name=elder.full_name,
            preferred_name=elder.preferred_name,
            phone_e164=elder.phone_e164,
            status=elder.status,
            my_role=role,
            created_at=elder.created_at,
        )


class RegistrationOut(BaseModel):
    result: Literal["created", "link_requested"]
    # Only for "created": a taken number reveals nothing about the existing elder.
    elder: ElderOut | None = None
