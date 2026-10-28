from typing import Any

from pydantic import BaseModel


class ClerkEvent(BaseModel):
    type: str
    data: dict[str, Any]


class ClerkUserData(BaseModel):
    id: str
    public_metadata: dict[str, Any] = {}
