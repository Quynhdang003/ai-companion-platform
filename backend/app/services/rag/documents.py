"""KB documents as admins manage them: list, read, add, edit, delete.

Saving embeds the document within the request (KB documents are short), before anything is
written: an embedding error leaves the stored version as it was. A saved document is
searchable by the next `search_knowledge` call.
"""

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass

from sqlalchemy import ScalarSelect, delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.llm.client import LLMClient
from app.models import KbChunk, KbDocument
from app.services.rag.ingest import add_document, update_document
from app.services.rag.search import fold

_TITLE_CONSTRAINT = "uq_kb_documents_title"


class TitleTakenError(ValueError):
    """Another document has this title."""


@dataclass(frozen=True)
class DocumentInfo:
    document: KbDocument
    # How many searchable pieces it was split into.
    chunk_count: int


def _chunk_count() -> ScalarSelect[int]:
    return (
        select(func.count())
        .where(KbChunk.document_id == KbDocument.id)
        .correlate(KbDocument)
        .scalar_subquery()
    )


async def list_documents(db: AsyncSession, *, query: str | None = None) -> list[DocumentInfo]:
    """Most recently changed first. `query` matches anywhere in the title, accents and case
    ignored ("so khan cap" finds "Số khẩn cấp")."""
    stmt = select(KbDocument, _chunk_count()).order_by(
        KbDocument.updated_at.desc(), KbDocument.title
    )
    if query:
        folded_title = func.immutable_unaccent(func.lower(KbDocument.title))
        stmt = stmt.where(folded_title.contains(fold(query.lower()), autoescape=True))
    return [DocumentInfo(document, count) for document, count in await db.execute(stmt)]


async def get_document(db: AsyncSession, document_id: uuid.UUID) -> DocumentInfo | None:
    stmt = (
        select(KbDocument, _chunk_count())
        .where(KbDocument.id == document_id)
        # Reload what an update in this session left stale (`updated_at`).
        .execution_options(populate_existing=True)
    )
    row = (await db.execute(stmt)).first()
    return DocumentInfo(row[0], row[1]) if row is not None else None


async def create_document(
    db: AsyncSession,
    llm: LLMClient,
    *,
    title: str,
    content: str,
    source: str | None,
    created_by: uuid.UUID,
) -> DocumentInfo:
    """Raises `TitleTakenError`, `EmptyDocumentError` or `LLMError` (nothing stored)."""
    await _check_title_free(db, title)
    with _title_conflict(title):
        async with db.begin_nested():
            document = await add_document(
                db, llm, title=title, content=content, source=source, created_by=created_by
            )
    info = await get_document(db, document.id)
    assert info is not None
    return info


async def edit_document(
    db: AsyncSession,
    llm: LLMClient,
    document_id: uuid.UUID,
    *,
    title: str,
    content: str,
    source: str | None,
) -> DocumentInfo | None:
    """None if there is no such document. Raises as `create_document` (nothing changed).

    The row stays locked while the new text is embedded, so two edits of one document
    can't mix their chunks.
    """
    document = await db.scalar(
        select(KbDocument).where(KbDocument.id == document_id).with_for_update()
    )
    if document is None:
        return None
    await _check_title_free(db, title, other_than=document_id)
    with _title_conflict(title):
        async with db.begin_nested():
            await update_document(db, llm, document, title=title, content=content, source=source)
    return await get_document(db, document_id)


async def delete_document(db: AsyncSession, document_id: uuid.UUID) -> bool:
    """Its chunks go with it (`ON DELETE CASCADE`). False if there was no such document."""
    stmt = delete(KbDocument).where(KbDocument.id == document_id).returning(KbDocument.id)
    return await db.scalar(stmt) is not None


async def _check_title_free(
    db: AsyncSession, title: str, *, other_than: uuid.UUID | None = None
) -> None:
    """Checked before embedding, so a taken title costs no embedding request."""
    stmt = select(KbDocument.id).where(KbDocument.title == title)
    if other_than is not None:
        stmt = stmt.where(KbDocument.id != other_than)
    if await db.scalar(stmt) is not None:
        raise TitleTakenError(title)


@contextmanager
def _title_conflict(title: str) -> Iterator[None]:
    """The unique title, for a document saved with the same title meanwhile."""
    try:
        yield
    except IntegrityError as exc:
        if _TITLE_CONSTRAINT in str(exc.orig):
            raise TitleTakenError(title) from exc
        raise
