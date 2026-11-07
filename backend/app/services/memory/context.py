"""What the call agent knows about an ACTIVE elder before it speaks (pre-call hook).

Read straight from `memories` with two indexed queries and no LLM, so the hook stays well
under its 500ms budget (architecture invariant 3).
"""

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Memory, MemoryCategory

SUMMARY_LIMIT = 8
SUMMARY_MAX_CHARS = 600
PLACES_LIMIT = 5


@dataclass(frozen=True)
class MemoryContext:
    # The most important facts (no places), as sentences: "Bà có con gái tên Mai. ..."
    summary: str | None
    # Most mentioned places: "Bệnh viện Bạch Mai: Bà hay đi khám ở đó; Nhà: ..."
    frequent_places: str | None


async def memory_context(db: AsyncSession, elder_id: uuid.UUID) -> MemoryContext:
    facts = await db.scalars(
        select(Memory.content)
        .where(Memory.elder_id == elder_id, Memory.category != MemoryCategory.PLACE)
        .order_by(Memory.importance.desc(), Memory.last_mentioned_at.desc())
        .limit(SUMMARY_LIMIT)
    )
    places = await db.execute(
        select(Memory.subject, Memory.content)
        .where(Memory.elder_id == elder_id, Memory.category == MemoryCategory.PLACE)
        .order_by(Memory.mention_count.desc(), Memory.last_mentioned_at.desc())
        .limit(PLACES_LIMIT)
    )
    return MemoryContext(
        summary=_summary(facts.all()),
        frequent_places="; ".join(
            f"{subject}: {content}" if subject else content for subject, content in places
        )
        or None,
    )


def _summary(sentences: list[str]) -> str | None:
    """Whole sentences only, up to SUMMARY_MAX_CHARS."""
    text = ""
    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence.endswith((".", "!", "?")):
            sentence += "."
        candidate = f"{text} {sentence}" if text else sentence
        if len(candidate) > SUMMARY_MAX_CHARS:
            break
        text = candidate
    return text or None
