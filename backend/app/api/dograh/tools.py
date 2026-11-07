"""HTTP tools the Dograh agent calls mid-call; the caller comes only from `session_token`."""

from fastapi import APIRouter, Depends

from app.core.db import DbSession
from app.core.dograh_auth import require_dograh_key
from app.core.errors import AppError
from app.models import CallSession
from app.schemas.dograh import ConfirmActivationOut, SessionToolRequest
from app.services.identity import call_sessions, elders
from app.services.identity.call_sessions import InvalidSessionError
from app.services.identity.elders import ActivationOutcome, ElderUnavailableError

router = APIRouter(prefix="/tools", tags=["dograh"], dependencies=[Depends(require_dograh_key)])

_ACTIVATION_MESSAGES = {
    ActivationOutcome.ACTIVATED: "Đã kích hoạt dịch vụ cho số điện thoại này.",
    ActivationOutcome.ALREADY_ACTIVE: "Dịch vụ đã được kích hoạt từ trước.",
}


async def _call_session(db: DbSession, token: str) -> CallSession:
    try:
        return await call_sessions.resolve(db, token)
    except InvalidSessionError as exc:
        raise AppError(401, "invalid_session", "Phiên gọi đã hết hạn, vui lòng gọi lại.") from exc


@router.post("/confirm-activation", response_model=ConfirmActivationOut)
async def confirm_activation(body: SessionToolRequest, db: DbSession) -> ConfirmActivationOut:
    """Call only after the elder has said yes to using the service."""
    call = await _call_session(db, body.session_token)
    try:
        activation = await elders.activate(db, call)
    except ElderUnavailableError as exc:
        raise AppError(
            404, "not_registered", "Số điện thoại này chưa được đăng ký dịch vụ."
        ) from exc
    await db.commit()

    elder = activation.elder
    return ConfirmActivationOut(
        status=activation.outcome.value,
        message=_ACTIVATION_MESSAGES[activation.outcome],
        preferred_name=elder.preferred_name or elder.full_name,
    )
