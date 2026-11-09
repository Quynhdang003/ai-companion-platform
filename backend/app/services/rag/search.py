"""Hybrid search over knowledge-base chunks, tolerant to missing diacritics and STT errors.

Three rankings, fused with Reciprocal Rank Fusion. Each one only keeps chunks that pass its
own relevance bar, so an unrelated question finds nothing:
- full-text: accent-free words (`simple` config, no stemming); a chunk must contain at least
  MIN_WORD_COVERAGE of the query's distinct words. Vietnamese words are single syllables
  ("nay", "nào", "bao"), so matching any one of them would match almost everything;
- trigram: `word_similarity` on accent-free lower-case text (typos, split words);
- vector: cosine distance to the query embedding, up to MAX_VECTOR_DISTANCE.

The thresholds were calibrated on the sample KB with real Gemini embeddings: related
questions sit at distance 0.22-0.37, unrelated ones (weather, gold price) at 0.41-0.44.

The query embedding runs alongside the SQL queries with a short timeout; if it fails or is
late, the search falls back to the two lexical rankings. `rrf_merge`, `fold` and
`query_words` are meant to be reused by other corpora (scam patterns).
"""

import asyncio
import logging
import math
import re
import unicodedata
import uuid
from collections import defaultdict
from collections.abc import Hashable, Sequence
from dataclasses import dataclass
from typing import TypeVar

from sqlalchemy import Integer, cast, func, literal, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.llm.client import LLMClient, LLMError
from app.models import KbChunk, KbDocument

logger = logging.getLogger(__name__)

RRF_K = 60
# Candidates taken from each ranking before fusion.
CANDIDATES = 20
MIN_WORD_COVERAGE = 0.6
MAX_QUERY_WORDS = 12
TRIGRAM_THRESHOLD = 0.5
# Cosine distance above which a chunk isn't considered related to the query.
MAX_VECTOR_DISTANCE = 0.40
QUERY_EMBED_TIMEOUT_SECONDS = 2.0

_WORDS = re.compile(r"[^\W_]+")

ItemT = TypeVar("ItemT", bound=Hashable)


@dataclass(frozen=True)
class KbHit:
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    title: str
    content: str
    score: float


def rrf_merge(rankings: Sequence[Sequence[ItemT]], k: int = RRF_K) -> list[tuple[ItemT, float]]:
    """Items by summed 1 / (k + rank) over the rankings, best first."""
    scores: defaultdict[ItemT, float] = defaultdict(float)
    for ranking in rankings:
        for rank, item in enumerate(ranking, start=1):
            scores[item] += 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda pair: pair[1], reverse=True)


def fold(text: str) -> str:
    """Strip Vietnamese diacritics like PostgreSQL's `unaccent`: 'Đường bệnh' -> 'Duong benh'."""
    text = text.replace("đ", "d").replace("Đ", "D")
    return "".join(c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn")


def query_words(query: str) -> list[str]:
    """Distinct accent-free lower-case words, at most MAX_QUERY_WORDS.

    'Bệnh viện ở đâu? Bệnh!' -> ['benh', 'vien', 'o', 'dau']. Only word characters survive,
    so tsquery operators in the input can't change the query.
    """
    return list(dict.fromkeys(_WORDS.findall(fold(query.lower()))))[:MAX_QUERY_WORDS]


async def search_kb(
    db: AsyncSession,
    llm: LLMClient,
    query: str,
    *,
    limit: int = 3,
    embed_timeout: float = QUERY_EMBED_TIMEOUT_SECONDS,
) -> list[KbHit]:
    query = " ".join(query.split())
    if not query:
        return []
    embedding = asyncio.create_task(_embed_query(llm, query, embed_timeout))
    rankings = [
        await fulltext_ids(db, query, CANDIDATES),
        await trigram_ids(db, query, CANDIDATES),
    ]
    vector = await embedding
    if vector is not None:
        rankings.append(await vector_ids(db, vector, CANDIDATES))

    best = rrf_merge(rankings)[:limit]
    if not best:
        return []
    rows = await db.execute(
        select(KbChunk.id, KbChunk.document_id, KbChunk.content, KbDocument.title)
        .join(KbDocument, KbDocument.id == KbChunk.document_id)
        .where(KbChunk.id.in_([chunk_id for chunk_id, _ in best]))
    )
    by_id = {row.id: row for row in rows}
    return [
        KbHit(
            chunk_id=chunk_id,
            document_id=by_id[chunk_id].document_id,
            title=by_id[chunk_id].title,
            content=by_id[chunk_id].content,
            score=score,
        )
        for chunk_id, score in best
    ]


async def fulltext_ids(db: AsyncSession, query: str, limit: int) -> list[uuid.UUID]:
    """Chunks containing at least MIN_WORD_COVERAGE of the query's words, most words first."""
    words = query_words(query)
    if not words:
        return []
    any_word = func.to_tsquery("simple", " | ".join(words))
    matched = sum(
        (
            cast(KbChunk.search_text.bool_op("@@")(func.to_tsquery("simple", word)), Integer)
            for word in words
        ),
        start=literal(0),
    )
    rows = await db.scalars(
        select(KbChunk.id)
        .where(
            KbChunk.search_text.bool_op("@@")(any_word),
            matched >= math.ceil(len(words) * MIN_WORD_COVERAGE),
        )
        .order_by(matched.desc(), func.ts_rank_cd(KbChunk.search_text, any_word).desc(), KbChunk.id)
        .limit(limit)
    )
    return list(rows.all())


async def trigram_ids(db: AsyncSession, query: str, limit: int) -> list[uuid.UUID]:
    needle = func.immutable_unaccent(func.lower(query))
    # Same expression as the trigram index (ix_kb_chunks_content_trgm), so `<%` can use it.
    haystack = func.immutable_unaccent(func.lower(KbChunk.content))
    await db.execute(
        select(func.set_config("pg_trgm.word_similarity_threshold", str(TRIGRAM_THRESHOLD), True))
    )
    rows = await db.scalars(
        select(KbChunk.id)
        .where(needle.bool_op("<%")(haystack))
        .order_by(func.word_similarity(needle, haystack).desc(), KbChunk.id)
        .limit(limit)
    )
    return list(rows.all())


async def vector_ids(db: AsyncSession, embedding: list[float], limit: int) -> list[uuid.UUID]:
    distance = KbChunk.embedding.cosine_distance(embedding)
    rows = await db.scalars(
        select(KbChunk.id)
        .where(distance <= MAX_VECTOR_DISTANCE)
        .order_by(distance, KbChunk.id)
        .limit(limit)
    )
    return list(rows.all())


async def _embed_query(llm: LLMClient, query: str, timeout: float) -> list[float] | None:
    try:
        [vector] = await asyncio.wait_for(llm.embed([query], task="query"), timeout)
    except (LLMError, TimeoutError) as exc:
        logger.warning("query embedding unavailable (%s): lexical search only", type(exc).__name__)
        return None
    return vector
