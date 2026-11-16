"""Store the scams elders were warned about: medium or high risk, ACTIVE elders only.

Callers who haven't consented (pending, unknown, blocked) still get the spoken warning,
but nothing is stored about them. Only codes are stored, never what the caller said.
"""

from sqlalchemy import and_, case, func, literal_column
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AlertStatus, CallSession, Elder, ElderStatus, RiskLevel, ScamEvent
from app.services.scam.engine import ScamAssessment


async def record(
    db: AsyncSession, call: CallSession, assessment: ScamAssessment
) -> ScamEvent | None:
    """Add or raise the call's event for this scam type (not committed); None if not stored.

    Repeated checks of one type in one call keep a single row: the level only goes up, the
    signals add up, and the family alert is queued once, when the level first becomes high.
    """
    if assessment.level.rank < RiskLevel.MEDIUM.rank or assessment.scam_type is None:
        return None
    if call.elder_id is None:
        return None
    elder = await db.get(Elder, call.elder_id)
    if elder is None or elder.status is not ElderStatus.ACTIVE:
        return None

    high = assessment.level is RiskLevel.HIGH
    stmt = insert(ScamEvent).values(
        call_session_id=call.id,
        elder_id=elder.id,
        scam_type=assessment.scam_type,
        risk_level=assessment.level,
        signals=sorted(signal.value for signal in assessment.signals),
        assessed_by=assessment.assessed_by,
        alert_status=AlertStatus.PENDING if high else None,
    )
    new = stmt.excluded
    becomes_high = and_(
        new.risk_level == RiskLevel.HIGH.value,
        ScamEvent.risk_level != RiskLevel.HIGH.value,
    )
    stmt = stmt.on_conflict_do_update(
        constraint="uq_scam_events_call_session_id_scam_type",
        set_={
            # Only medium and high are stored, so "either is high" is the higher level.
            "risk_level": case(
                (new.risk_level == RiskLevel.HIGH.value, RiskLevel.HIGH.value),
                else_=ScamEvent.risk_level,
            ),
            "assessed_by": case((becomes_high, new.assessed_by), else_=ScamEvent.assessed_by),
            "signals": literal_column(
                "ARRAY(SELECT DISTINCT s FROM unnest(scam_events.signals || excluded.signals) s"
                " ORDER BY s)"
            ),
            "alert_status": case(
                (
                    and_(new.risk_level == RiskLevel.HIGH.value, ScamEvent.alert_status.is_(None)),
                    AlertStatus.PENDING.value,
                ),
                else_=ScamEvent.alert_status,
            ),
            "updated_at": func.now(),
        },
    )
    return await db.scalar(stmt.returning(ScamEvent), execution_options={"populate_existing": True})
