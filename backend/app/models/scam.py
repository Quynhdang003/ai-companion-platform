import uuid
from datetime import datetime
from enum import StrEnum

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Computed,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column

from app.llm.embeddings import EMBEDDING_DIMS
from app.models.base import Base, TimestampMixin


class ScamType(StrEnum):
    """The scams the engine knows (the KB scam doc has one section each), plus `other`.

    Adding a type needs a migration that widens the `CHECK` constraints using it.
    """

    POLICE_IMPERSONATION = "police_impersonation"
    BANK_IMPERSONATION = "bank_impersonation"
    RELATIVE_IMPERSONATION = "relative_impersonation"
    INVESTMENT = "investment"
    HEALTH_PRODUCT = "health_product"
    RESORT_CONTRACT = "resort_contract"
    FAKE_CHARITY = "fake_charity"
    OTHER = "other"


class RiskLevel(StrEnum):
    """How likely what the caller describes is a scam, lowest first.

    - high: a clear scam: money, codes, personal data or an app/link is asked for under a
      scam story or pressure. The family is alerted.
    - medium: signs of a scam (a scam story, pressure, claims too good to be true), but
      nothing asked yet, or not clear enough to be sure.
    - low: unusual but probably harmless; the caller is told to be careful.
    - none: no sign of a scam.
    """

    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"

    @property
    def rank(self) -> int:
        return _LEVEL_ORDER.index(self)


_LEVEL_ORDER = list(RiskLevel)


class Signal(StrEnum):
    """A sign of a scam in what the caller describes.

    Layer-1 rules find them from phrases (`app/services/scam/rules.py`), the classifier
    names them too, and scam events store their codes: never the caller's words.
    """

    # What the caller is asked to do.
    MONEY_TRANSFER = "money_transfer"
    CREDENTIALS = "credentials"  # OTP, password, PIN, card security code
    PERSONAL_INFO = "personal_info"  # ID or account number, balance, face scan
    LINK_OR_APP = "link_or_app"
    SAFE_ACCOUNT = "safe_account"  # money "held for the investigation"
    PERSONAL_ACCOUNT = "personal_account"  # pay into a private or stranger's account
    # Pressure.
    URGENCY = "urgency"
    SECRECY = "secrecy"
    THREAT = "threat"
    # Who they claim to be or what they offer: these point to a scam type.
    AUTHORITY = "authority"
    BANK = "bank"
    RELATIVE = "relative"  # "cháu đây", a new number, a relative's hacked account
    RELATIVE_EMERGENCY = "relative_emergency"
    INVESTMENT = "investment"
    EASY_PROFIT = "easy_profit"
    HEALTH_PRODUCT = "health_product"
    MIRACLE_CURE = "miracle_cure"
    PRIZE = "prize"
    RESORT = "resort"
    DONATION = "donation"
    SERVICE = "service"  # utilities, social insurance, tax, parcels, money sent by mistake


def scam_type_column() -> Enum:
    # Room for longer type names added later without widening the column.
    return Enum(
        ScamType,
        name="scam_type",
        native_enum=False,
        create_constraint=True,
        length=40,
        values_callable=lambda e: [m.value for m in e],
    )


class ScamPattern(TimestampMixin, Base):
    """A known scam script: what the scammer says and asks for. Managed by admins.

    The scam engine retrieves the patterns closest to what the caller describes and shows
    them to the classifier. One pattern is one search unit (short, no chunking).
    """

    __tablename__ = "scam_patterns"
    __table_args__ = (
        Index("ix_scam_patterns_search_text", "search_text", postgresql_using="gin"),
        Index(
            "ix_scam_patterns_embedding",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    scam_type: Mapped[ScamType] = mapped_column(scam_type_column())
    title: Mapped[str] = mapped_column(Text, unique=True)
    content: Mapped[str] = mapped_column(Text)
    # Where it came from (seed file, URL), for admins.
    source: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    # Accent-free tokens of title + content, for phrase queries on word pairs.
    search_text: Mapped[str] = mapped_column(
        TSVECTOR,
        Computed(
            "to_tsvector('simple', immutable_unaccent(title || ' ' || content))", persisted=True
        ),
    )
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIMS))


class AssessedBy(StrEnum):
    """What decided a scam verdict (`app/services/scam/engine.py`)."""

    RULES = "rules"  # a decisive layer-1 rule
    LLM = "llm"  # the classifier
    RULES_FALLBACK = "rules_fallback"  # the classifier failed or ran out of time


class AlertStatus(StrEnum):
    """Family alert of a high-risk scam event (Telegram, `notification/scam_alerts.py`)."""

    PENDING = "pending"
    SENT = "sent"  # at least one family member got it
    FAILED = "failed"  # every send failed, up to the job's maximum of attempts
    SKIPPED = "skipped"  # nobody to alert: no family member connected Telegram, or too late


def _str_enum(enum: type[StrEnum], name: str) -> Enum:
    return Enum(
        enum,
        name=name,
        native_enum=False,
        create_constraint=True,
        values_callable=lambda e: [m.value for m in e],
    )


class ScamEvent(TimestampMixin, Base):
    """A scam the elder was warned about during a call: medium or high risk, ACTIVE elders only.

    One row per call and scam type: a later check of the same type in the same call raises
    the level (never lowers it) and adds its signals. Nothing the caller said is stored:
    only the type, the level, signal codes and who decided. `created_at` is when the elder
    was first warned. Family sees these (type, level, time); high risk alerts them.
    """

    __tablename__ = "scam_events"
    __table_args__ = (
        UniqueConstraint(
            "call_session_id", "scam_type", name="uq_scam_events_call_session_id_scam_type"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    call_session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("call_sessions.id", ondelete="CASCADE")
    )
    elder_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("elders.id", ondelete="CASCADE"), index=True
    )
    scam_type: Mapped[ScamType] = mapped_column(scam_type_column())
    risk_level: Mapped[RiskLevel] = mapped_column(_str_enum(RiskLevel, "risk_level"))
    # `Signal` codes, sorted.
    signals: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default=text("'{}'"))
    assessed_by: Mapped[AssessedBy] = mapped_column(_str_enum(AssessedBy, "assessed_by"))
    # Set to pending when the level becomes high; None = no alert needed.
    alert_status: Mapped[AlertStatus | None] = mapped_column(_str_enum(AlertStatus, "alert_status"))
    # Alert sends that all failed so far; `failed` once it reaches the job's maximum.
    alert_attempts: Mapped[int] = mapped_column(server_default=text("0"))
    alerted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
