import uuid
from datetime import datetime
from typing import Annotated, Self

from pydantic import BaseModel, StringConstraints, field_validator

from app.services.rag.documents import DocumentInfo

# Limits the admin form shows too (`frontend/lib/api/schemas.ts`). 20 000 characters is about
# 25 chunks: one embedding request.
TITLE_MAX = 200
CONTENT_MAX = 20_000
SOURCE_MAX = 500

Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=TITLE_MAX)]
Content = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=CONTENT_MAX)
]
Source = Annotated[str, StringConstraints(strip_whitespace=True, max_length=SOURCE_MAX)]


class KbDocumentIn(BaseModel):
    title: Title
    content: Content
    # Where it came from (file name, URL), for admins; blank means none.
    source: Source | None = None

    @field_validator("source")
    @classmethod
    def _blank_to_none(cls, value: str | None) -> str | None:
        return value or None


class KbDocumentSummaryOut(BaseModel):
    id: uuid.UUID
    title: str
    source: str | None
    chunk_count: int
    created_at: datetime
    updated_at: datetime

    @classmethod
    def build(cls, info: DocumentInfo) -> Self:
        document = info.document
        return cls(
            id=document.id,
            title=document.title,
            source=document.source,
            chunk_count=info.chunk_count,
            created_at=document.created_at,
            updated_at=document.updated_at,
        )


class KbDocumentOut(KbDocumentSummaryOut):
    content: str

    @classmethod
    def build(cls, info: DocumentInfo) -> Self:
        summary = KbDocumentSummaryOut.build(info)
        return cls(**summary.model_dump(), content=info.document.content)
