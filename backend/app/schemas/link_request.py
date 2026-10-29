import uuid
from datetime import datetime
from typing import Self

from pydantic import BaseModel

from app.models import Elder, ElderLinkRequest, LinkRequestStatus, User


class ElderRef(BaseModel):
    id: uuid.UUID
    full_name: str


class RequesterOut(BaseModel):
    # Null until the Clerk webhook has synced the user.
    display_name: str | None
    email: str | None


class IncomingRequestOut(BaseModel):
    id: uuid.UUID
    elder: ElderRef
    requester: RequesterOut
    created_at: datetime

    @classmethod
    def build(cls, request: ElderLinkRequest, elder: Elder, requester: User) -> Self:
        return cls(
            id=request.id,
            elder=ElderRef(id=elder.id, full_name=elder.full_name),
            requester=RequesterOut(display_name=requester.display_name, email=requester.email),
            created_at=request.created_at,
        )


class OutgoingRequestOut(BaseModel):
    id: uuid.UUID
    # The number the requester typed in; the elder's name is shown only once approved.
    phone_e164: str
    status: LinkRequestStatus
    elder_full_name: str | None
    created_at: datetime
    decided_at: datetime | None

    @classmethod
    def build(cls, request: ElderLinkRequest, elder: Elder) -> Self:
        approved = request.status is LinkRequestStatus.APPROVED
        return cls(
            id=request.id,
            phone_e164=elder.phone_e164,
            status=request.status,
            elder_full_name=elder.full_name if approved else None,
            created_at=request.created_at,
            decided_at=request.decided_at,
        )


class LinkRequestDecisionOut(BaseModel):
    id: uuid.UUID
    status: LinkRequestStatus
    decided_at: datetime | None
