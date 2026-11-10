import uuid
from enum import StrEnum

from pgvector.sqlalchemy import Vector
from sqlalchemy import Computed, Enum, ForeignKey, Index, Text, Uuid, text
from sqlalchemy.dialects.postgresql import TSVECTOR
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
