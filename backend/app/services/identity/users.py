"""Web users (family/admin) synced from Clerk."""

from collections.abc import Mapping
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User, UserRole
from app.schemas.clerk import ClerkEvent, ClerkUserData


def role_from_metadata(public_metadata: Mapping[str, Any]) -> UserRole:
    """Role from Clerk `publicMetadata.role`; anything missing or unknown is `family`."""
    try:
        return UserRole(public_metadata.get("role"))
    except ValueError:
        return UserRole.FAMILY


async def get_or_create(db: AsyncSession, clerk_user_id: str) -> User:
    """User for a verified Clerk id, created as `family` if the webhook hasn't synced it yet."""
    await db.execute(
        insert(User)
        .values(clerk_user_id=clerk_user_id)
        .on_conflict_do_nothing(index_elements=[User.clerk_user_id])
    )
    return await db.scalar(select(User).where(User.clerk_user_id == clerk_user_id))


async def upsert_from_clerk(db: AsyncSession, data: ClerkUserData) -> User:
    synced = {
        "role": role_from_metadata(data.public_metadata),
        "display_name": data.display_name,
        "email": data.primary_email,
    }
    stmt = (
        insert(User)
        .values(clerk_user_id=data.id, **synced)
        .on_conflict_do_update(
            index_elements=[User.clerk_user_id],
            set_={**synced, "updated_at": func.now()},
        )
        .returning(User)
    )
    return await db.scalar(stmt, execution_options={"populate_existing": True})


async def delete_by_clerk_id(db: AsyncSession, clerk_user_id: str) -> None:
    # FK cascade removes the user's elder_family links; the elders themselves stay.
    await db.execute(delete(User).where(User.clerk_user_id == clerk_user_id))


async def apply_clerk_event(db: AsyncSession, event: ClerkEvent) -> None:
    """Apply a verified Clerk webhook event; event types other than user.* are ignored."""
    if event.type in ("user.created", "user.updated"):
        await upsert_from_clerk(db, ClerkUserData.model_validate(event.data))
    elif event.type == "user.deleted":
        data = ClerkUserData.model_validate(event.data)
        await delete_by_clerk_id(db, data.id)
