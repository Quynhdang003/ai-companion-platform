"""Hybrid search over scam patterns: which known scams look like what the caller describes.

The query is a situation (a few sentences the call agent writes about what the caller was
told or asked to do), not a short question, so the lexical ranking differs from the KB's:
- full-text: pairs of consecutive words within a clause ("tai khoan", "khoan tam",
  "tam giu"), each a phrase query. Most Vietnamese words have two syllables, so a pair
  carries meaning that a single syllable doesn't. Pairs with a function word ("tien vao",
  "vao tai") are dropped: they would make any money transfer look like every scam. A
  pattern must share at least MIN_PAIR_MATCHES pairs with the situation;
- vector: cosine distance to the situation's embedding, up to MAX_VECTOR_DISTANCE.

There is no trigram ranking: the agent's LLM writes the situation, so there are no STT
typos to absorb, and `word_similarity` says little about a needle several sentences long.

The thresholds were calibrated on the seed patterns with real Gemini embeddings:
- situations of a few sentences (two per type, `other` included): the right type is
  nearest at distance 0.18-0.25 (nearest other type 0.25-0.36) and shares 5-12 word pairs;
- one-line situations ("Người ta hỏi mã OTP của bác."): 0.22-0.33, and only 1-3 pairs, so
  the vector ranking does the work;
- unrelated talk (weather, gold price, booking a ride): 0.40-0.45 and no pairs, so nothing.
Harmless look-alikes (a grandchild asking for school fees, a temple's donation box) can
still retrieve patterns: these are references for the classifier, which decides the risk.

The situation embedding runs alongside the SQL query with a short timeout; if it fails or
is late, only the word-pair ranking is used.
"""

import asyncio
import re
import uuid
from dataclasses import dataclass

from sqlalchemy import Integer, cast, func, literal, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.llm.client import LLMClient
from app.models import ScamPattern, ScamType
from app.services.rag.search import (
    QUERY_EMBED_TIMEOUT_SECONDS,
    embed_query,
    fold,
    rrf_merge,
    words,
)

# Candidates taken from each ranking before fusion.
CANDIDATES = 20
MAX_SITUATION_PAIRS = 60
MIN_PAIR_MATCHES = 3
# Cosine distance above which a pattern isn't considered close to the situation.
MAX_VECTOR_DISTANCE = 0.35

# Accent-free function words. Only words that stay function words once accents are gone:
# "la" (là / lạ: "số lạ"), "bi" (bị / bí mật), "lai" (lại / lãi), "no" (nó / nợ) and
# "khong" ("không rủi ro") are kept.
STOPWORDS = frozenset(
    "va voi cua cho thi o vao ra se duoc nay nhung cac mot cung rat nua rang khi ay a nhe "
    "roi phai gi nao ai".split()
)

# Punctuation ends a clause: no word pair spans it.
_CLAUSE_BREAK = re.compile(r"[^\w\s]+")


@dataclass(frozen=True)
class PatternHit:
    pattern_id: uuid.UUID
    scam_type: ScamType
    title: str
    content: str
    score: float


def word_pairs(text: str, limit: int = MAX_SITUATION_PAIRS) -> list[str]:
    """Distinct pairs of consecutive accent-free words within a clause, in order, without
    pairs that contain a STOPWORDS word.

    'Chuyển tiền vào tài khoản lạ, gấp!' -> ['chuyen tien', 'tai khoan', 'khoan la']:
    "tien vao" and "vao tai" hold "vao", and "la gap" spans the comma.
    """
    pairs: dict[str, None] = {}
    # Fold first: decomposed diacritics aren't word characters and would split words.
    for clause in _CLAUSE_BREAK.split(fold(text)):
        clause_words = words(clause)
        for first, second in zip(clause_words, clause_words[1:], strict=False):
            if first not in STOPWORDS and second not in STOPWORDS:
                pairs[f"{first} {second}"] = None
    return list(pairs)[:limit]


async def search_patterns(
    db: AsyncSession,
    llm: LLMClient,
    situation: str,
    *,
    limit: int = 3,
    embed_timeout: float = QUERY_EMBED_TIMEOUT_SECONDS,
) -> list[PatternHit]:
    situation = " ".join(situation.split())
    if not situation:
        return []
    embedding = asyncio.create_task(embed_query(llm, situation, embed_timeout))
    rankings = [await pair_ids(db, situation, CANDIDATES)]
    vector = await embedding
    if vector is not None:
        rankings.append(await vector_ids(db, vector, CANDIDATES))

    best = rrf_merge(rankings)[:limit]
    if not best:
        return []
    rows = await db.execute(
        select(ScamPattern.id, ScamPattern.scam_type, ScamPattern.title, ScamPattern.content).where(
            ScamPattern.id.in_([pattern_id for pattern_id, _ in best])
        )
    )
    by_id = {row.id: row for row in rows}
    return [
        PatternHit(
            pattern_id=pattern_id,
            scam_type=by_id[pattern_id].scam_type,
            title=by_id[pattern_id].title,
            content=by_id[pattern_id].content,
            score=score,
        )
        for pattern_id, score in best
    ]


async def pair_ids(db: AsyncSession, situation: str, limit: int) -> list[uuid.UUID]:
    """Patterns sharing at least MIN_PAIR_MATCHES word pairs with the situation, most first."""
    phrases = [pair.replace(" ", " <-> ") for pair in word_pairs(situation)]
    if not phrases:
        return []
    any_pair = func.to_tsquery("simple", " | ".join(f"({phrase})" for phrase in phrases))
    matched = sum(
        (
            cast(ScamPattern.search_text.bool_op("@@")(func.to_tsquery("simple", phrase)), Integer)
            for phrase in phrases
        ),
        start=literal(0),
    )
    rows = await db.scalars(
        select(ScamPattern.id)
        .where(ScamPattern.search_text.bool_op("@@")(any_pair), matched >= MIN_PAIR_MATCHES)
        .order_by(
            matched.desc(),
            func.ts_rank_cd(ScamPattern.search_text, any_pair).desc(),
            ScamPattern.id,
        )
        .limit(limit)
    )
    return list(rows.all())


async def vector_ids(db: AsyncSession, embedding: list[float], limit: int) -> list[uuid.UUID]:
    distance = ScamPattern.embedding.cosine_distance(embedding)
    rows = await db.scalars(
        select(ScamPattern.id)
        .where(distance <= MAX_VECTOR_DISTANCE)
        .order_by(distance, ScamPattern.id)
        .limit(limit)
    )
    return list(rows.all())
