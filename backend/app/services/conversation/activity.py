"""Call activity for the family: when the elder called, for how long, and scam alerts.

Metadata only: never transcripts, recordings or memories (architecture invariant 9).

Only calls from the one in which the elder consented on (user decision, 2026-11-16): a
caller who never agreed, or calls before agreeing (declined ones included), stay unseen,
even after consent. The consent call is the elder's latest call that started before
`consent_at`: consent is given during a call.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import ColumnElement, and_, false, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import CallLog, CallSession, Elder, RiskLevel, ScamEvent, ScamType

WEEK = timedelta(days=7)
MONTH = timedelta(days=30)


@dataclass(frozen=True)
class ScamAlert:
    scam_type: ScamType
    risk_level: RiskLevel
    created_at: datetime


@dataclass(frozen=True)
class CallItem:
    id: uuid.UUID
    started_at: datetime
    # None while the call is on, or if Dograh never reported its end.
    duration_seconds: int | None
    scam_alerts: list[ScamAlert]


@dataclass(frozen=True)
class CallPage:
    calls: list[CallItem]
    # Pass as `before` for the next page; None on the last one.
    next_before: datetime | None


@dataclass(frozen=True)
class Summary:
    calls_7d: int
    calls_30d: int
    scam_alerts_30d: int
    last_call_at: datetime | None


def _visible(elder: Elder) -> ColumnElement[bool]:
    """The elder's calls from the consent call on; none before consent."""
    if elder.consent_at is None:
        return false()
    consent_call_start = (
        select(func.max(CallSession.started_at))
        .where(CallSession.elder_id == elder.id, CallSession.started_at <= elder.consent_at)
        .scalar_subquery()
    )
    return and_(
        CallSession.elder_id == elder.id,
        CallSession.started_at >= func.coalesce(consent_call_start, elder.consent_at),
    )


async def calls(
    db: AsyncSession, elder: Elder, *, limit: int, before: datetime | None = None
) -> CallPage:
    """The elder's visible calls, newest first, `limit` at a time."""
    stmt = (
        select(CallSession.id, CallSession.started_at, CallLog.duration_seconds)
        .outerjoin(CallLog, CallLog.call_session_id == CallSession.id)
        .where(_visible(elder))
        .order_by(CallSession.started_at.desc())
        .limit(limit + 1)
    )
    if before is not None:
        stmt = stmt.where(CallSession.started_at < before)
    rows = (await db.execute(stmt)).all()
    more = len(rows) > limit
    rows = rows[:limit]

    alerts: dict[uuid.UUID, list[ScamAlert]] = {row.id: [] for row in rows}
    if alerts:
        events = await db.execute(
            select(
                ScamEvent.call_session_id,
                ScamEvent.scam_type,
                ScamEvent.risk_level,
                ScamEvent.created_at,
            )
            .where(ScamEvent.call_session_id.in_(alerts))
            .order_by(ScamEvent.created_at)
        )
        for call_id, scam_type, level, created_at in events:
            alerts[call_id].append(ScamAlert(scam_type, level, created_at))

    return CallPage(
        calls=[
            CallItem(row.id, row.started_at, row.duration_seconds, alerts[row.id]) for row in rows
        ],
        next_before=rows[-1].started_at if more else None,
    )


async def summary(db: AsyncSession, elder: Elder, *, now: datetime) -> Summary:
    """How often the elder called in the last 7 and 30 days, and scam alerts in 30 days."""
    counts = (
        await db.execute(
            select(
                func.count().filter(CallSession.started_at >= now - WEEK),
                func.count().filter(CallSession.started_at >= now - MONTH),
                func.max(CallSession.started_at),
            ).where(_visible(elder))
        )
    ).one()
    # Scam events exist only for consented (ACTIVE) elders, from consent on.
    scam_alerts = await db.scalar(
        select(func.count()).where(
            ScamEvent.elder_id == elder.id, ScamEvent.created_at >= now - MONTH
        )
    )
    return Summary(
        calls_7d=counts[0],
        calls_30d=counts[1],
        scam_alerts_30d=scam_alerts or 0,
        last_call_at=counts[2],
    )
