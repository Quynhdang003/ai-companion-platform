"""Scam Risk Engine: one verdict for what the caller describes, within a time budget.

1. Layer-1 rules (`rules.py`). A decisive rule means high risk at once: no pattern search,
   no LLM.
2. Otherwise the known patterns closest to the situation are retrieved (`search.py`) and
   the classifier (`classifier.py`) decides, with the layer-1 signals as hints.
3. If the classifier fails (error, rate limit, no key, invalid output) or the budget runs
   out, the layer-1 result stands. The engine never raises an LLM error: a caller in the
   middle of a scam always gets an answer.

Logs carry the level, type, who decided and the latency, never the situation.
"""

import asyncio
import logging
import time
from dataclasses import dataclass
from enum import StrEnum

from sqlalchemy.ext.asyncio import AsyncSession

from app.llm.client import LLMClient, LLMError, LLMNotConfiguredError, LLMRateLimitedError
from app.models import RiskLevel, ScamType, Signal
from app.services.scam.classifier import classify
from app.services.scam.rules import RuleResult, assess_rules
from app.services.scam.search import search_patterns

logger = logging.getLogger(__name__)

PATTERN_LIMIT = 3
# Situation embedding for the pattern search; past it, word pairs only.
EMBED_TIMEOUT_SECONDS = 1.5
# Less budget than this left for the classifier: don't start it.
MIN_CLASSIFIER_SECONDS = 0.5


class AssessedBy(StrEnum):
    RULES = "rules"  # a decisive rule
    LLM = "llm"  # the classifier
    RULES_FALLBACK = "rules_fallback"  # the classifier failed or ran out of time


class FallbackReason(StrEnum):
    TIMEOUT = "timeout"
    RATE_LIMITED = "rate_limited"
    NOT_CONFIGURED = "not_configured"
    ERROR = "error"  # API error or output outside the schema


@dataclass(frozen=True)
class ScamAssessment:
    level: RiskLevel
    # Set for medium and high only.
    scam_type: ScamType | None
    signals: frozenset[Signal]
    assessed_by: AssessedBy
    decisive_rule: str | None = None
    fallback_reason: FallbackReason | None = None
    # Titles of the patterns shown to the classifier, best first (for evaluation).
    pattern_titles: tuple[str, ...] = ()
    # The classifier's one-sentence reason: for evaluation only, never stored or logged.
    reason: str | None = None


async def assess(
    db: AsyncSession, llm: LLMClient, situation: str, *, timeout: float
) -> ScamAssessment:
    started = time.monotonic()
    situation = " ".join(situation.split())
    rules = assess_rules(situation)
    if rules.decisive:
        return _log(
            started,
            ScamAssessment(
                level=rules.level,
                scam_type=rules.scam_type,
                signals=rules.signals,
                assessed_by=AssessedBy.RULES,
                decisive_rule=rules.decisive_rule,
            ),
        )

    deadline = started + timeout
    patterns = await search_patterns(
        db,
        llm,
        situation,
        limit=PATTERN_LIMIT,
        embed_timeout=min(EMBED_TIMEOUT_SECONDS, timeout),
    )
    titles = tuple(hit.title for hit in patterns)
    remaining = deadline - time.monotonic()
    if remaining < MIN_CLASSIFIER_SECONDS:
        return _log(started, _fallback(rules, FallbackReason.TIMEOUT, titles))
    try:
        verdict = await asyncio.wait_for(
            classify(llm, situation, patterns, rules.signals), remaining
        )
    except TimeoutError:
        return _log(started, _fallback(rules, FallbackReason.TIMEOUT, titles))
    except LLMRateLimitedError:
        return _log(started, _fallback(rules, FallbackReason.RATE_LIMITED, titles))
    except LLMNotConfiguredError:
        return _log(started, _fallback(rules, FallbackReason.NOT_CONFIGURED, titles))
    except LLMError as exc:
        # LLMError messages never carry prompt text (`app/llm/client.py`).
        logger.warning("scam classifier failed: %s", exc)
        return _log(started, _fallback(rules, FallbackReason.ERROR, titles))

    return _log(
        started,
        ScamAssessment(
            level=verdict.risk_level,
            scam_type=verdict.scam_type,
            signals=rules.signals | frozenset(verdict.signals),
            assessed_by=AssessedBy.LLM,
            pattern_titles=titles,
            reason=verdict.reason or None,
        ),
    )


def _fallback(rules: RuleResult, reason: FallbackReason, titles: tuple[str, ...]) -> ScamAssessment:
    scam_type = rules.scam_type if rules.level.rank >= RiskLevel.MEDIUM.rank else None
    return ScamAssessment(
        level=rules.level,
        scam_type=scam_type,
        signals=rules.signals,
        assessed_by=AssessedBy.RULES_FALLBACK,
        fallback_reason=reason,
        pattern_titles=titles,
    )


def _log(started: float, assessment: ScamAssessment) -> ScamAssessment:
    logger.info(
        "scam check: %s %s by %s%s in %.2f s",
        assessment.level.value,
        assessment.scam_type.value if assessment.scam_type else "-",
        assessment.assessed_by.value,
        f" ({assessment.fallback_reason.value})" if assessment.fallback_reason else "",
        time.monotonic() - started,
    )
    return assessment
