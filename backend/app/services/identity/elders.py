"""Elder registration by family members and activation on the first call (flow A)."""

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    CallSession,
    Elder,
    ElderFamily,
    ElderLinkRequest,
    ElderStatus,
    FamilyRole,
    User,
)


class RegistrationOutcome(StrEnum):
    CREATED = "created"
    LINK_REQUESTED = "link_requested"
    ALREADY_LINKED = "already_linked"


@dataclass(frozen=True)
class Registration:
    outcome: RegistrationOutcome
    # Only set for CREATED: a taken number must not reveal the existing elder's data.
    elder: Elder | None = None


async def register(
    db: AsyncSession,
    user: User,
    *,
    full_name: str,
    phone_e164: str,
    preferred_name: str | None,
) -> Registration:
    """New number → elder (PENDING_VERIFICATION) owned by `user`; taken number → link request."""
    # ON CONFLICT keeps concurrent registrations of the same number from failing.
    elder = await db.scalar(
        insert(Elder)
        .values(phone_e164=phone_e164, full_name=full_name, preferred_name=preferred_name)
        .on_conflict_do_nothing(index_elements=[Elder.phone_e164])
        .returning(Elder)
    )
    if elder is not None:
        db.add(ElderFamily(elder_id=elder.id, user_id=user.id, role=FamilyRole.OWNER))
        await db.flush()
        return Registration(RegistrationOutcome.CREATED, elder)

    elder_id = await db.scalar(select(Elder.id).where(Elder.phone_e164 == phone_e164))
    linked = await db.scalar(
        select(ElderFamily.role).where(
            ElderFamily.elder_id == elder_id, ElderFamily.user_id == user.id
        )
    )
    if linked is not None:
        return Registration(RegistrationOutcome.ALREADY_LINKED)

    # Re-sending while a request is still pending is a no-op (partial unique index).
    await db.execute(
        insert(ElderLinkRequest)
        .values(elder_id=elder_id, requester_id=user.id)
        .on_conflict_do_nothing(
            index_elements=[ElderLinkRequest.elder_id, ElderLinkRequest.requester_id],
            index_where=text("status = 'pending'"),
        )
    )
    return Registration(RegistrationOutcome.LINK_REQUESTED)


async def list_for_user(db: AsyncSession, user: User) -> list[tuple[Elder, FamilyRole]]:
    """Elders linked to `user`, with the user's role for each, oldest link first."""
    result = await db.execute(
        select(Elder, ElderFamily.role)
        .join(ElderFamily, ElderFamily.elder_id == Elder.id)
        .where(ElderFamily.user_id == user.id)
        .order_by(ElderFamily.created_at)
    )
    return list(result.all())


class ActivationOutcome(StrEnum):
    ACTIVATED = "activated"
    ALREADY_ACTIVE = "already_active"


@dataclass(frozen=True)
class Activation:
    outcome: ActivationOutcome
    elder: Elder


class ElderUnavailableError(Exception):
    """The call belongs to no registered elder (unknown or blocked caller)."""


async def activate(db: AsyncSession, call: CallSession) -> Activation:
    """Record the consent given on `call`: PENDING_VERIFICATION → ACTIVE with `consent_at`.

    Calling it again is a no-op, so the agent may confirm twice.
    """
    if call.elder_id is None:
        raise ElderUnavailableError
    elder = await db.scalar(
        select(Elder)
        .where(Elder.id == call.elder_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if elder is None or elder.status is ElderStatus.BLOCKED:
        raise ElderUnavailableError
    if elder.status is ElderStatus.ACTIVE:
        return Activation(ActivationOutcome.ALREADY_ACTIVE, elder)

    elder.status = ElderStatus.ACTIVE
    elder.consent_at = datetime.now(UTC)
    await db.flush()
    return Activation(ActivationOutcome.ACTIVATED, elder)
