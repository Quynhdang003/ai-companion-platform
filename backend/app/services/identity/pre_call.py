"""Pre-call hook: identify the caller by number and open the call's session (flow B).

Runs before the agent speaks (Dograh waits up to 10s, our target is < 500ms): one indexed
lookup, no LLM calls.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Elder, ElderFamily, ElderStatus, FamilyRole, User
from app.schemas.dograh import CallerStatus, CallInbound, InitialContext
from app.services.identity import call_sessions
from app.services.identity.phone import InvalidPhoneError, normalize_vn_phone


async def build_context(db: AsyncSession, call: CallInbound) -> InitialContext:
    raw_number = call.from_number or ""
    try:
        from_number = normalize_vn_phone(raw_number)
    except InvalidPhoneError:
        # Web calls without caller_number, hidden or foreign numbers: never registered.
        from_number, elder = raw_number, None
    else:
        elder = await db.scalar(select(Elder).where(Elder.phone_e164 == from_number))
    if elder is not None and elder.status is ElderStatus.BLOCKED:
        elder = None

    # Unknown and blocked callers get a session too, but it reaches no elder data.
    token = await call_sessions.start(
        db,
        elder_id=elder.id if elder else None,
        from_number=from_number,
        workflow_run_id=call.workflow_run_id,
    )
    if elder is None:
        return InitialContext(
            session_token=token, caller_status=CallerStatus.UNKNOWN, is_registered=False
        )
    if elder.status is ElderStatus.ACTIVE:
        return InitialContext(
            session_token=token,
            caller_status=CallerStatus.ACTIVE,
            is_registered=True,
            full_name=elder.full_name,
            preferred_name=elder.preferred_name or elder.full_name,
        )
    # PENDING_VERIFICATION: before consent the agent only learns who registered the number.
    return InitialContext(
        session_token=token,
        caller_status=CallerStatus.PENDING_CONSENT,
        is_registered=True,
        registered_by=await _owner_name(db, elder.id),
    )


async def _owner_name(db: AsyncSession, elder_id: uuid.UUID) -> str | None:
    """Null if the owner's name isn't synced from Clerk yet, or the owner deleted their account."""
    return await db.scalar(
        select(User.display_name)
        .join(ElderFamily, ElderFamily.user_id == User.id)
        .where(ElderFamily.elder_id == elder_id, ElderFamily.role == FamilyRole.OWNER)
    )
