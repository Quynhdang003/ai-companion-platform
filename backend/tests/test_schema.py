import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import delete, func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from alembic import command
from app.models import CallSession, Elder, ElderFamily, ElderStatus, FamilyRole, User
from tests.conftest import alembic_config


def make_call_session(elder_id: uuid.UUID | None) -> CallSession:
    return CallSession(
        elder_id=elder_id,
        session_token_hash=uuid.uuid4().hex,
        from_number="+84912345678",
        expires_at=datetime.now(UTC) + timedelta(minutes=30),
    )


def test_migration_round_trip_matches_models(migrated_db: str) -> None:
    config = alembic_config(migrated_db)

    command.downgrade(config, "base")
    command.upgrade(config, "head")
    command.check(config)


async def test_new_elder_gets_server_defaults(session: AsyncSession) -> None:
    elder = Elder(phone_e164="+84912345678", full_name="Nguyễn Văn A")
    session.add(elder)
    await session.flush()

    assert isinstance(elder.id, uuid.UUID)
    assert elder.status is ElderStatus.PENDING_VERIFICATION
    assert elder.profile == {}
    assert elder.consent_at is None


async def test_duplicate_phone_is_rejected(session: AsyncSession) -> None:
    session.add(Elder(phone_e164="+84912345678", full_name="A"))
    await session.flush()

    session.add(Elder(phone_e164="+84912345678", full_name="B"))
    with pytest.raises(IntegrityError, match="uq_elders_phone_e164"):
        await session.flush()


@pytest.mark.parametrize("phone", ["0912345678", "84912345678", "+0912345678", "+84 912 345"])
async def test_non_e164_phone_is_rejected(session: AsyncSession, phone: str) -> None:
    session.add(Elder(phone_e164=phone, full_name="A"))

    with pytest.raises(IntegrityError, match="ck_elders_phone_e164_format"):
        await session.flush()


@pytest.mark.parametrize(
    ("statement", "constraint"),
    [
        (
            "INSERT INTO elders (phone_e164, full_name, status) "
            "VALUES ('+84912345678', 'A', 'DELETED')",
            "ck_elders_status",
        ),
        ("INSERT INTO users (clerk_user_id, role) VALUES ('u1', 'owner')", "ck_users_role"),
    ],
)
async def test_unknown_enum_value_is_rejected(
    session: AsyncSession, statement: str, constraint: str
) -> None:
    with pytest.raises(IntegrityError, match=constraint):
        await session.execute(text(statement))


async def test_deleting_elder_cascades(session: AsyncSession) -> None:
    elder = Elder(phone_e164="+84912345678", full_name="A")
    user = User(clerk_user_id="user_1")
    session.add_all([elder, user])
    await session.flush()
    session.add_all(
        [
            ElderFamily(elder_id=elder.id, user_id=user.id, role=FamilyRole.OWNER),
            make_call_session(elder.id),
        ]
    )
    await session.flush()

    await session.execute(delete(Elder).where(Elder.id == elder.id))

    assert await session.scalar(select(func.count()).select_from(ElderFamily)) == 0
    assert await session.scalar(select(func.count()).select_from(CallSession)) == 0
    assert await session.get(User, user.id) is not None


async def test_call_session_allows_unknown_caller(session: AsyncSession) -> None:
    call = make_call_session(elder_id=None)
    session.add(call)
    await session.flush()

    assert isinstance(call.id, uuid.UUID)
    assert call.started_at is not None
