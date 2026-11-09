"""Turn one call's transcript into memories: add new facts, update the ones the call repeats."""

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.llm.client import LLMClient
from app.llm.prompts import memory_extraction
from app.llm.schemas.memory import ExtractedMemory, MemoryExtraction
from app.models import CallLog, Memory

# Existing memories shown to the model, so it updates them instead of adding duplicates.
MAX_EXISTING = 50


@dataclass(frozen=True)
class ExtractionResult:
    added: int
    updated: int


async def extract_call_memories(
    db: AsyncSession, llm: LLMClient, log: CallLog, elder_id: uuid.UUID, call_date: date
) -> ExtractionResult:
    """Apply the model's add/update list to the elder's memories (not committed).

    Nothing in the session changes until the output is valid and every changed memory is
    embedded; LLM errors propagate to the caller.
    """
    existing = (
        await db.scalars(
            select(Memory)
            .where(Memory.elder_id == elder_id)
            .order_by(Memory.importance.desc(), Memory.last_mentioned_at.desc())
            .limit(MAX_EXISTING)
        )
    ).all()
    refs = {f"m{i}": memory for i, memory in enumerate(existing, start=1)}
    extraction = await llm.generate_json(
        memory_extraction.build_prompt(call_date, refs, log.transcript or []),
        MemoryExtraction,
        system=memory_extraction.SYSTEM,
    )

    plan = _plan(extraction, refs)
    if not plan:
        return ExtractionResult(added=0, updated=0)
    vectors = await llm.embed([_embedding_text(item) for _, item in plan], task="document")

    now = datetime.now(UTC)
    for (target, item), vector in zip(plan, vectors, strict=True):
        if target is None:
            memory = Memory(elder_id=elder_id, mention_count=1)
            db.add(memory)
        else:
            memory = target
            memory.mention_count += 1
        memory.category = item.category
        memory.subject = item.subject
        memory.content = item.content
        memory.importance = item.importance
        memory.last_mentioned_at = now
        memory.source_call_log_id = log.id
        memory.embedding = vector
    added = sum(1 for target, _ in plan if target is None)
    return ExtractionResult(added=added, updated=len(plan) - added)


def _plan(
    extraction: MemoryExtraction, refs: dict[str, Memory]
) -> list[tuple[Memory | None, ExtractedMemory]]:
    """(existing memory or None for a new one, item); an unknown ref becomes an add, and
    repeated updates of one memory keep the last."""
    plan: list[tuple[Memory | None, ExtractedMemory]] = []
    position: dict[str, int] = {}
    for item in extraction.memories:
        ref = item.ref or ""
        target = refs.get(ref) if item.action == "update" else None
        if target is None:
            plan.append((None, item))
        elif ref in position:
            plan[position[ref]] = (target, item)
        else:
            position[ref] = len(plan)
            plan.append((target, item))
    return plan


def _embedding_text(item: ExtractedMemory) -> str:
    return f"{item.subject}: {item.content}" if item.subject else item.content
