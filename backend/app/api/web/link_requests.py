import uuid

from fastapi import APIRouter

from app.core.auth import FamilyUser
from app.core.db import DbSession
from app.core.errors import AppError
from app.models import User
from app.schemas.link_request import (
    IncomingRequestOut,
    LinkRequestDecisionOut,
    OutgoingRequestOut,
)
from app.services.identity import link_requests
from app.services.identity.link_requests import RequestAlreadyDecidedError, RequestNotFoundError

router = APIRouter(prefix="/api/link-requests", tags=["web"])


@router.get("/incoming", response_model=list[IncomingRequestOut])
async def list_incoming(user: FamilyUser, db: DbSession) -> list[IncomingRequestOut]:
    rows = await link_requests.list_incoming(db, user)
    return [IncomingRequestOut.build(*row) for row in rows]


@router.get("/outgoing", response_model=list[OutgoingRequestOut])
async def list_outgoing(user: FamilyUser, db: DbSession) -> list[OutgoingRequestOut]:
    rows = await link_requests.list_outgoing(db, user)
    return [OutgoingRequestOut.build(*row) for row in rows]


@router.post("/{request_id}/approve", response_model=LinkRequestDecisionOut)
async def approve(request_id: uuid.UUID, user: FamilyUser, db: DbSession) -> LinkRequestDecisionOut:
    return await _decide(db, user, request_id, approve=True)


@router.post("/{request_id}/reject", response_model=LinkRequestDecisionOut)
async def reject(request_id: uuid.UUID, user: FamilyUser, db: DbSession) -> LinkRequestDecisionOut:
    return await _decide(db, user, request_id, approve=False)


async def _decide(
    db: DbSession, user: User, request_id: uuid.UUID, *, approve: bool
) -> LinkRequestDecisionOut:
    try:
        request = await link_requests.decide(db, user, request_id, approve=approve)
    except RequestNotFoundError as exc:
        raise AppError(404, "not_found", "Link request not found") from exc
    except RequestAlreadyDecidedError as exc:
        raise AppError(409, "already_decided", "Link request was already decided") from exc
    await db.commit()
    return LinkRequestDecisionOut(
        id=request.id, status=request.status, decided_at=request.decided_at
    )
