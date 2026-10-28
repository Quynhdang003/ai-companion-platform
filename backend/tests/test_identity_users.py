import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import UserRole
from app.schemas.clerk import ClerkUserData
from app.services.identity import users


async def test_get_or_create_is_idempotent(session: AsyncSession) -> None:
    first = await users.get_or_create(session, "user_1")
    second = await users.get_or_create(session, "user_1")

    assert first.id == second.id
    assert first.role is UserRole.FAMILY


async def test_upsert_keeps_id_and_updates_role(session: AsyncSession) -> None:
    created = await users.upsert_from_clerk(session, ClerkUserData(id="user_2"))
    updated = await users.upsert_from_clerk(
        session, ClerkUserData(id="user_2", public_metadata={"role": "admin"})
    )

    assert updated.id == created.id
    assert updated.role is UserRole.ADMIN


async def test_upsert_syncs_name_and_primary_email(session: AsyncSession) -> None:
    data = ClerkUserData(
        id="user_3",
        first_name=" Hoa ",
        last_name="Nguyễn",
        email_addresses=[
            {"id": "e1", "email_address": "old@example.com"},
            {"id": "e2", "email_address": "hoa@example.com"},
        ],
        primary_email_address_id="e2",
    )

    user = await users.upsert_from_clerk(session, data)

    assert user.display_name == "Hoa Nguyễn"
    assert user.email == "hoa@example.com"

    cleared = await users.upsert_from_clerk(session, ClerkUserData(id="user_3", first_name=" "))
    assert cleared.display_name is None
    assert cleared.email is None


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
