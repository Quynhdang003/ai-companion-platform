"""Link requests: an elder's owner approves or rejects other family members."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import ColumnElement, and_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Elder, ElderFamily, ElderLinkRequest, FamilyRole, LinkRequestStatus, User


class RequestNotFoundError(Exception):
    """Missing, or not on an elder the user owns (indistinguishable on purpose)."""


class RequestAlreadyDecidedError(Exception):
    pass


def _owned_by(owner: User) -> ColumnElement[bool]:
    """Join condition: the request's elder is owned by `owner`."""
    return and_(
        ElderFamily.elder_id == ElderLinkRequest.elder_id,
        ElderFamily.user_id == owner.id,
        ElderFamily.role == FamilyRole.OWNER,
    )


async def list_incoming(
    db: AsyncSession, owner: User
) -> list[tuple[ElderLinkRequest, Elder, User]]:
    """Pending requests on elders `owner` owns, with the elder and the requester."""
    result = await db.execute(
        select(ElderLinkRequest, Elder, User)
        .join(ElderFamily, _owned_by(owner))
        .join(Elder, Elder.id == ElderLinkRequest.elder_id)
        .join(User, User.id == ElderLinkRequest.requester_id)
        .where(ElderLinkRequest.status == LinkRequestStatus.PENDING)
        .order_by(ElderLinkRequest.created_at)
    )
    return list(result.all())


async def list_outgoing(db: AsyncSession, requester: User) -> list[tuple[ElderLinkRequest, Elder]]:
    """Requests sent by `requester`, newest first."""
    result = await db.execute(
        select(ElderLinkRequest, Elder)
        .join(Elder, Elder.id == ElderLinkRequest.elder_id)
        .where(ElderLinkRequest.requester_id == requester.id)
        .order_by(ElderLinkRequest.created_at.desc())
    )
    return list(result.all())


async def decide(
    db: AsyncSession, owner: User, request_id: uuid.UUID, *, approve: bool
) -> ElderLinkRequest:
    """Approve (requester becomes a viewer) or reject a pending request on an owned elder."""
    request = await db.scalar(
        select(ElderLinkRequest)
        .join(ElderFamily, _owned_by(owner))
        .where(ElderLinkRequest.id == request_id)
        .with_for_update(of=ElderLinkRequest)
        .execution_options(populate_existing=True)
    )
    if request is None:
        raise RequestNotFoundError
    if request.status is not LinkRequestStatus.PENDING:
        raise RequestAlreadyDecidedError

    if approve:
        await db.execute(
            insert(ElderFamily)
            .values(elder_id=request.elder_id, user_id=request.requester_id, role=FamilyRole.VIEWER)
            .on_conflict_do_nothing(index_elements=[ElderFamily.elder_id, ElderFamily.user_id])
        )
    request.status = LinkRequestStatus.APPROVED if approve else LinkRequestStatus.REJECTED
    request.decided_by = owner.id
    request.decided_at = datetime.now(UTC)
    await db.flush()
    return request
