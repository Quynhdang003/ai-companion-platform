"""Add or replace scam patterns, embedding every new or changed one in a single request.

Patterns are embedded before anything is written, so an embedding error leaves the stored
versions untouched.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.llm.client import LLMClient
from app.models import ScamPattern, ScamType
from app.services.rag.ingest import SyncResult, embedding_text

# A pattern is one search unit (no chunking), so it stays as short as a KB chunk.
MAX_PATTERN_CHARS = 800
MAX_TITLE_CHARS = 200


class InvalidPatternError(ValueError):
    """Empty or too long text, or the same title given twice."""


@dataclass(frozen=True)
class PatternIn:
    scam_type: ScamType
    title: str
    content: str
    source: str | None = None


async def sync_patterns(
    db: AsyncSession, llm: LLMClient, patterns: Sequence[PatternIn]
) -> list[SyncResult]:
    """Create each pattern, or update the stored one with its title in place (not committed).

    Only new patterns and changed content are embedded: a new type or source alone isn't.
    Results are in input order.
    """
    _validate(patterns)
    stored = {
        row.title: row
        for row in await db.scalars(
            select(ScamPattern).where(ScamPattern.title.in_([p.title for p in patterns]))
        )
    }
    to_embed = [
        p for p in patterns if p.title not in stored or stored[p.title].content != p.content
    ]
    vectors = (
        await llm.embed([embedding_text(p.title, p.content) for p in to_embed], task="document")
        if to_embed
        else []
    )
    embedded = {p.title: vector for p, vector in zip(to_embed, vectors, strict=True)}

    results: list[SyncResult] = []
    for pattern in patterns:
        row = stored.get(pattern.title)
        if row is None:
            db.add(
                ScamPattern(
                    scam_type=pattern.scam_type,
                    title=pattern.title,
                    content=pattern.content,
                    source=pattern.source,
                    embedding=embedded[pattern.title],
                )
            )
            results.append(SyncResult.CREATED)
        elif (row.scam_type, row.content, row.source) == (
            pattern.scam_type,
            pattern.content,
            pattern.source,
        ):
            results.append(SyncResult.UNCHANGED)
        else:
            row.scam_type = pattern.scam_type
            row.content = pattern.content
            row.source = pattern.source
            if pattern.title in embedded:
                row.embedding = embedded[pattern.title]
            results.append(SyncResult.UPDATED)
    await db.flush()
    return results


def _validate(patterns: Sequence[PatternIn]) -> None:
    seen: set[str] = set()
    for pattern in patterns:
        if not pattern.title.strip() or not pattern.content.strip():
            raise InvalidPatternError("pattern needs a title and content")
        if len(pattern.title) > MAX_TITLE_CHARS:
            raise InvalidPatternError(f"title over {MAX_TITLE_CHARS} characters: {pattern.title}")
        if len(pattern.content) > MAX_PATTERN_CHARS:
            raise InvalidPatternError(
                f"content over {MAX_PATTERN_CHARS} characters: {pattern.title}"
            )
        if pattern.title in seen:
            raise InvalidPatternError(f"title given twice: {pattern.title}")
        seen.add(pattern.title)
