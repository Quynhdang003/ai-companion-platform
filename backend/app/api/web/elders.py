from fastapi import APIRouter, Response, status

from app.core.auth import FamilyUser
from app.core.db import DbSession
from app.core.errors import AppError
from app.models import FamilyRole
from app.schemas.elder import ElderCreate, ElderOut, RegistrationOut
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
