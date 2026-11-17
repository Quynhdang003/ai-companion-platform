import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status

from app.core.auth import AdminUser
from app.core.db import DbSession
from app.core.errors import AppError
from app.llm.client import LLMClient, LLMError, LLMNotConfiguredError, get_llm_client
from app.schemas.kb import KbDocumentIn, KbDocumentOut, KbDocumentSummaryOut
from app.services.rag import documents
from app.services.rag.documents import DocumentInfo, TitleTakenError
from app.services.rag.ingest import EmptyDocumentError

router = APIRouter(prefix="/api/admin/kb/documents", tags=["admin"])

Llm = Annotated[LLMClient, Depends(get_llm_client)]


@router.get("", response_model=list[KbDocumentSummaryOut])
async def list_documents(
    _: AdminUser,
    db: DbSession,
    q: Annotated[str | None, Query(max_length=200)] = None,
) -> list[KbDocumentSummaryOut]:
    """Every document (the KB is small), most recently changed first; `q` searches titles."""
    found = await documents.list_documents(db, query=(q or "").strip() or None)
    return [KbDocumentSummaryOut.build(info) for info in found]


@router.get("/{document_id}", response_model=KbDocumentOut)
async def get_document(document_id: uuid.UUID, _: AdminUser, db: DbSession) -> KbDocumentOut:
    return KbDocumentOut.build(_found(await documents.get_document(db, document_id)))


@router.post("", status_code=status.HTTP_201_CREATED, response_model=KbDocumentOut)
async def create_document(
    body: KbDocumentIn, user: AdminUser, db: DbSession, llm: Llm
) -> KbDocumentOut:
    """Stored, chunked and embedded at once: searchable as soon as this returns."""
    with _save_errors():
        info = await documents.create_document(
            db, llm, title=body.title, content=body.content, source=body.source, created_by=user.id
        )
    await db.commit()
    return KbDocumentOut.build(info)


@router.put("/{document_id}", response_model=KbDocumentOut)
async def update_document(
    document_id: uuid.UUID, body: KbDocumentIn, _: AdminUser, db: DbSession, llm: Llm
) -> KbDocumentOut:
    """Replaces title, text and source; re-embedded only if the title or the text changed."""
    with _save_errors():
        info = await documents.edit_document(
            db, llm, document_id, title=body.title, content=body.content, source=body.source
        )
    found = _found(info)
    await db.commit()
    return KbDocumentOut.build(found)


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(document_id: uuid.UUID, _: AdminUser, db: DbSession) -> Response:
    if not await documents.delete_document(db, document_id):
        raise AppError(404, "not_found", "Document not found")
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _found(info: DocumentInfo | None) -> DocumentInfo:
    if info is None:
        raise AppError(404, "not_found", "Document not found")
    return info


@contextmanager
def _save_errors() -> Iterator[None]:
    """Nothing is stored or changed when any of these is raised."""
    try:
        yield
    except TitleTakenError as exc:
        raise AppError(409, "title_taken", "Another document has this title") from exc
    except EmptyDocumentError as exc:
        raise AppError(422, "empty_document", "The document has no text to index") from exc
    except LLMNotConfiguredError as exc:
        raise AppError(500, "llm_not_configured", "Embeddings are not configured") from exc
    except LLMError as exc:
        raise AppError(
            503, "embedding_unavailable", "Could not embed the document; nothing was saved"
        ) from exc
