"""Add or replace knowledge-base documents: chunk, embed in one batch, store.

Chunks are embedded before anything is written, so an embedding error leaves the stored
version untouched.
"""

import uuid
from enum import StrEnum

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.llm.client import LLMClient
from app.models import KbChunk, KbDocument
from app.services.rag.chunking import chunk_text


class EmptyDocumentError(ValueError):
    """The document has no text to index."""


class SyncResult(StrEnum):
    CREATED = "created"
    UPDATED = "updated"
    UNCHANGED = "unchanged"


def embedding_text(title: str, chunk: str) -> str:
    """The title gives a chunk its context ("Số khẩn cấp" + "113: công an ...")."""
    return f"{title}\n{chunk}"


async def add_document(
    db: AsyncSession,
    llm: LLMClient,
    *,
    title: str,
    content: str,
    source: str | None = None,
    created_by: uuid.UUID | None = None,
) -> KbDocument:
    chunks = await _embedded_chunks(llm, title, content)
    document = KbDocument(title=title, content=content, source=source, created_by=created_by)
    db.add(document)
    await db.flush()
    _add_chunks(db, document.id, chunks)
    await db.flush()
    return document


async def sync_document(
    db: AsyncSession, llm: LLMClient, *, title: str, content: str, source: str | None = None
) -> SyncResult:
    """Create the document with this title, or replace its text and chunks in place.

    Unchanged text and source skip re-embedding (seeding the same files twice costs nothing).
    """
    document = await db.scalar(select(KbDocument).where(KbDocument.title == title))
    if document is None:
        await add_document(db, llm, title=title, content=content, source=source)
        return SyncResult.CREATED
    if document.content == content and document.source == source:
        return SyncResult.UNCHANGED

    chunks = await _embedded_chunks(llm, title, content)
    document.content = content
    document.source = source
    await db.execute(delete(KbChunk).where(KbChunk.document_id == document.id))
    _add_chunks(db, document.id, chunks)
    await db.flush()
    return SyncResult.UPDATED


async def _embedded_chunks(
    llm: LLMClient, title: str, content: str
) -> list[tuple[str, list[float]]]:
    chunks = chunk_text(content)
    if not chunks:
        raise EmptyDocumentError("document has no text")
    vectors = await llm.embed([embedding_text(title, c) for c in chunks], task="document")
    return list(zip(chunks, vectors, strict=True))


def _add_chunks(
    db: AsyncSession, document_id: uuid.UUID, chunks: list[tuple[str, list[float]]]
) -> None:
    db.add_all(
        KbChunk(document_id=document_id, chunk_index=i, content=chunk, embedding=vector)
        for i, (chunk, vector) in enumerate(chunks)
    )
