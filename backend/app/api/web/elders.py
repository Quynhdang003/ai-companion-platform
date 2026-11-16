import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Query, Response, status
from pydantic import AwareDatetime

from app.core.auth import FamilyUser
from app.core.db import DbSession
from app.core.errors import AppError
from app.models import Elder, FamilyRole
from app.schemas.elder import CallPageOut, ElderCreate, ElderDetailOut, ElderOut, RegistrationOut
from app.services.conversation import activity
from app.services.identity import elders
from app.services.identity.elders import RegistrationOutcome
from app.services.identity.phone import InvalidPhoneError, normalize_vn_phone

router = APIRouter(prefix="/api/elders", tags=["web"])


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=RegistrationOut,
    responses={status.HTTP_202_ACCEPTED: {"model": RegistrationOut}},
)
async def register_elder(
    body: ElderCreate, user: FamilyUser, db: DbSession, response: Response
) -> RegistrationOut:
    """201 with the new elder, or 202 when the number is taken and a link request was sent."""
    try:
        phone_e164 = normalize_vn_phone(body.phone)
    except InvalidPhoneError as exc:
        raise AppError(422, "invalid_phone", "Not a valid Vietnamese phone number") from exc

    registration = await elders.register(
        db,
        user,
        full_name=body.full_name,
        phone_e164=phone_e164,
        preferred_name=body.preferred_name,
    )
    if registration.outcome is RegistrationOutcome.ALREADY_LINKED:
        raise AppError(409, "already_linked", "You are already linked to this elder")
    await db.commit()

    if registration.elder is not None:
        return RegistrationOut(
            result="created", elder=ElderOut.from_link(registration.elder, FamilyRole.OWNER)
        )
    response.status_code = status.HTTP_202_ACCEPTED
    return RegistrationOut(result="link_requested")


@router.get("", response_model=list[ElderOut])
async def list_elders(user: FamilyUser, db: DbSession) -> list[ElderOut]:
    return [ElderOut.from_link(elder, role) for elder, role in await elders.list_for_user(db, user)]


async def _linked(db: DbSession, user: FamilyUser, elder_id: uuid.UUID) -> tuple[Elder, FamilyRole]:
    """404 for an elder the user isn't linked to, whether or not it exists."""
    linked = await elders.linked_elder(db, user, elder_id)
    if linked is None:
        raise AppError(404, "not_found", "Elder not found")
    return linked


@router.get("/{elder_id}", response_model=ElderDetailOut)
async def get_elder(elder_id: uuid.UUID, user: FamilyUser, db: DbSession) -> ElderDetailOut:
    """Profile and call activity counts, for a family member linked to the elder."""
    elder, role = await _linked(db, user, elder_id)
    summary = await activity.summary(db, elder, now=datetime.now(UTC))
    return ElderDetailOut.build(elder, role, summary)


@router.get("/{elder_id}/calls", response_model=CallPageOut)
async def list_calls(
    elder_id: uuid.UUID,
    user: FamilyUser,
    db: DbSession,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
    before: Annotated[AwareDatetime | None, Query()] = None,
) -> CallPageOut:
    """The elder's calls, newest first: time, duration, scam alerts. Never what was said."""
    elder, _ = await _linked(db, user, elder_id)
    return CallPageOut.build(await activity.calls(db, elder, limit=limit, before=before))
