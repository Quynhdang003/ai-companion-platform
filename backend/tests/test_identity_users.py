import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import UserRole
from app.services.identity import users


async def test_get_or_create_is_idempotent(session: AsyncSession) -> None:
    first = await users.get_or_create(session, "user_1")
    second = await users.get_or_create(session, "user_1")

    assert first.id == second.id
    assert first.role is UserRole.FAMILY


async def test_upsert_keeps_id_and_updates_role(session: AsyncSession) -> None:
    created = await users.upsert_from_clerk(session, "user_2", {})
    updated = await users.upsert_from_clerk(session, "user_2", {"role": "admin"})

    assert updated.id == created.id
    assert updated.role is UserRole.ADMIN


@pytest.mark.parametrize(
    ("metadata", "expected"),
    [
        ({"role": "admin"}, UserRole.ADMIN),
        ({"role": "family"}, UserRole.FAMILY),
        ({"role": "ADMIN"}, UserRole.FAMILY),
        ({"role": 1}, UserRole.FAMILY),
        ({}, UserRole.FAMILY),
    ],
)
def test_role_from_metadata(metadata: dict[str, object], expected: UserRole) -> None:
    assert users.role_from_metadata(metadata) is expected
