"""Layer 2 of the Scam Risk Engine: Gemini classifies the situation, shown the known scam
patterns closest to it and the layer-1 signals as hints."""

from collections.abc import Sequence

from app.llm.client import LLMClient
from app.llm.prompts import scam_classification
from app.llm.schemas.scam import ScamClassification
from app.models import Signal
from app.services.scam.search import PatternHit


async def classify(
    llm: LLMClient,
    situation: str,
    patterns: Sequence[PatternHit],
    keyword_signals: frozenset[Signal],
) -> ScamClassification:
    """The model's validated verdict; LLM errors propagate to the caller."""
    return await llm.generate_json(
        scam_classification.build_prompt(situation, patterns, keyword_signals),
        ScamClassification,
        system=scam_classification.SYSTEM,
    )
