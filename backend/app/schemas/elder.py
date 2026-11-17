import uuid
from datetime import datetime
from typing import Annotated, Literal, Self

from pydantic import BaseModel, StringConstraints, field_validator

from app.models import Elder, ElderStatus, FamilyRole, RiskLevel, ScamType
from app.services.conversation.activity import CallItem, CallPage, Summary

FullName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
PreferredName = Annotated[str, StringConstraints(strip_whitespace=True, max_length=50)]
RawPhone = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=32)]


class ElderCreate(BaseModel):
    full_name: FullName
    # Normalized to E.164 by the route.
    phone: RawPhone
    preferred_name: PreferredName | None = None

    @field_validator("preferred_name")
    @classmethod
    def _blank_to_none(cls, value: str | None) -> str | None:
        return value or None


class ElderOut(BaseModel):
    id: uuid.UUID
    full_name: str
    preferred_name: str | None
    phone_e164: str
    status: ElderStatus
    my_role: FamilyRole
    created_at: datetime

    @classmethod
    def from_link(cls, elder: Elder, role: FamilyRole) -> Self:
        return cls(
            id=elder.id,
            full_name=elder.full_name,
            preferred_name=elder.preferred_name,
            phone_e164=elder.phone_e164,
            status=elder.status,
            my_role=role,
            created_at=elder.created_at,
        )


class RegistrationOut(BaseModel):
    result: Literal["created", "link_requested"]
    # Only for "created": a taken number reveals nothing about the existing elder.
    elder: ElderOut | None = None


class ActivitySummaryOut(BaseModel):
    calls_7d: int
    calls_30d: int
    scam_alerts_30d: int
    last_call_at: datetime | None


class ElderDetailOut(ElderOut):
    """An elder for a linked family member: profile and call activity counts."""

    # When the elder agreed to the service in a call; null before.
    consent_at: datetime | None
    activity: ActivitySummaryOut

    @classmethod
    def build(cls, elder: Elder, role: FamilyRole, summary: Summary) -> Self:
        return cls(
            **ElderOut.from_link(elder, role).model_dump(),
            consent_at=elder.consent_at,
            activity=ActivitySummaryOut(
                calls_7d=summary.calls_7d,
                calls_30d=summary.calls_30d,
                scam_alerts_30d=summary.scam_alerts_30d,
                last_call_at=summary.last_call_at,
            ),
        )


class ScamAlertOut(BaseModel):
    scam_type: ScamType
    risk_level: RiskLevel
    # When the elder was first warned in that call.
    created_at: datetime


class CallOut(BaseModel):
    """A call's metadata: never what was said."""

    id: uuid.UUID
    started_at: datetime
    # Null while the call is on, or if its end was never reported.
    duration_seconds: int | None
    scam_alerts: list[ScamAlertOut]

    @classmethod
    def build(cls, call: CallItem) -> Self:
        return cls(
            id=call.id,
            started_at=call.started_at,
            duration_seconds=call.duration_seconds,
            scam_alerts=[
                ScamAlertOut(
                    scam_type=a.scam_type, risk_level=a.risk_level, created_at=a.created_at
                )
                for a in call.scam_alerts
            ],
        )


class CallPageOut(BaseModel):
    calls: list[CallOut]
    # Pass as `before` for the next page; null on the last one.
    next_before: datetime | None

    @classmethod
    def build(cls, page: CallPage) -> Self:
        return cls(calls=[CallOut.build(c) for c in page.calls], next_before=page.next_before)
