from typing import Any

from pydantic import BaseModel


class ClerkEvent(BaseModel):
    type: str
    data: dict[str, Any]


class ClerkEmailAddress(BaseModel):
    id: str
    email_address: str


class ClerkUserData(BaseModel):
    id: str
    public_metadata: dict[str, Any] = {}
    first_name: str | None = None
    last_name: str | None = None
    email_addresses: list[ClerkEmailAddress] = []
    primary_email_address_id: str | None = None

    @property
    def display_name(self) -> str | None:
        name = " ".join(part.strip() for part in (self.first_name, self.last_name) if part)
        return name or None

    @property
    def primary_email(self) -> str | None:
        primary_id = self.primary_email_address_id
        return next((e.email_address for e in self.email_addresses if e.id == primary_id), None)
