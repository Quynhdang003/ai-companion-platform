from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class CallInbound(BaseModel):
    """Call fields of Dograh's pre-call request; `agent_id` and `to_number` are ignored."""

    # Numeric in Dograh, stored as text.
    workflow_run_id: str | None = None
    # Missing or empty for web calls without a `caller_number` context variable.
    from_number: str | None = Field(default=None, max_length=32)

    @field_validator("workflow_run_id", mode="before")
    @classmethod
    def _run_id_as_text(cls, value: object) -> object:
        return str(value) if isinstance(value, int) else value


class PreCallRequest(BaseModel):
    """`{"event": "call_inbound", "call_inbound": {...}}`; `event` is not checked."""

    call_inbound: CallInbound


class CallerStatus(StrEnum):
    ACTIVE = "active"
    PENDING_CONSENT = "pending_consent"
    UNKNOWN = "unknown"


class InitialContext(BaseModel):
    """Variables for Dograh prompts (`{{preferred_name | bác}}`) and tool presets
    (`{{initial_context.session_token}}`). Unset fields are left out of the response."""

    session_token: str
    caller_status: CallerStatus
    is_registered: bool
    # ACTIVE only: no personal data before consent.
    full_name: str | None = None
    preferred_name: str | None = None
    # PENDING_VERIFICATION only: the owner's name, so the agent can say who registered.
    registered_by: str | None = None


class PreCallResponse(BaseModel):
    initial_context: InitialContext


class SessionToolRequest(BaseModel):
    """Body of every Dograh tool; the token comes from a Preset Parameter, never the LLM."""

    session_token: str = Field(min_length=1, max_length=128)


class ConfirmActivationOut(BaseModel):
    status: Literal["activated", "already_active"]
    # Short, speakable Vietnamese for the agent.
    message: str
    preferred_name: str
