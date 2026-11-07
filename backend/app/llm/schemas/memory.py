from typing import Literal

from pydantic import BaseModel, Field

from app.models.memory import MemoryCategory


class ExtractedMemory(BaseModel):
    action: Literal["add", "update"]
    ref: str | None = Field(
        default=None,
        description='For "update": the ref of the existing memory (e.g. "m3"); null for "add".',
    )
    category: MemoryCategory
    subject: str | None = Field(
        default=None,
        max_length=120,
        description="Short name of the person, place or thing; null if none.",
    )
    content: str = Field(
        min_length=1,
        max_length=400,
        description="One short Vietnamese sentence about the elder, in the third person.",
    )
    importance: int = Field(ge=1, le=5, description="5 = health, safety or close family.")


class MemoryExtraction(BaseModel):
    memories: list[ExtractedMemory] = Field(default_factory=list, max_length=20)
