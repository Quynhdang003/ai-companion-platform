"""HTTP tools the Dograh agent calls mid-call; the caller comes only from `session_token`."""

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.dograh.session import resolve_call
from app.core.config import get_settings
from app.core.db import DbSession
from app.core.dograh_auth import require_dograh_key
from app.core.errors import AppError
from app.llm.client import LLMClient, get_llm_client, get_scam_llm_client
from app.schemas.dograh import (
    CheckScamOut,
    CheckScamRequest,
    ConfirmActivationOut,
    KnowledgeResult,
    SearchKnowledgeOut,
    SearchKnowledgeRequest,
    SessionToolRequest,
)
from app.services.identity import elders
from app.services.identity.elders import ActivationOutcome, ElderUnavailableError
from app.services.rag.search import search_kb
from app.services.scam import engine, events
from app.services.scam.warnings import warning_message

router = APIRouter(prefix="/tools", tags=["dograh"], dependencies=[Depends(require_dograh_key)])

_ACTIVATION_MESSAGES = {
    ActivationOutcome.ACTIVATED: "Đã kích hoạt dịch vụ cho số điện thoại này.",
    ActivationOutcome.ALREADY_ACTIVE: "Dịch vụ đã được kích hoạt từ trước.",
}

KNOWLEDGE_RESULTS = 3
_KNOWLEDGE_FOUND = "Dạ, con tìm được thông tin rồi ạ."
_KNOWLEDGE_NOT_FOUND = "Dạ, con chưa có thông tin về việc này ạ."


@router.post("/confirm-activation", response_model=ConfirmActivationOut)
async def confirm_activation(body: SessionToolRequest, db: DbSession) -> ConfirmActivationOut:
    """Call only after the elder has said yes to using the service."""
    call = await resolve_call(db, body.session_token)
    try:
        activation = await elders.activate(db, call)
    except ElderUnavailableError as exc:
        raise AppError(
            404, "not_registered", "Số điện thoại này chưa được đăng ký dịch vụ."
        ) from exc
    await db.commit()

    elder = activation.elder
    return ConfirmActivationOut(
        status=activation.outcome.value,
        message=_ACTIVATION_MESSAGES[activation.outcome],
        preferred_name=elder.preferred_name or elder.full_name,
    )


@router.post("/search-knowledge", response_model=SearchKnowledgeOut)
async def search_knowledge(
    body: SearchKnowledgeRequest,
    db: DbSession,
    llm: Annotated[LLMClient, Depends(get_llm_client)],
) -> SearchKnowledgeOut:
    """Knowledge-base passages for the caller's question.

    Open to every live call, registered or not: the KB holds no personal data.
    """
    await resolve_call(db, body.session_token)
    hits = await search_kb(db, llm, body.query, limit=KNOWLEDGE_RESULTS)
    return SearchKnowledgeOut(
        found=bool(hits),
        message=_KNOWLEDGE_FOUND if hits else _KNOWLEDGE_NOT_FOUND,
        results=[KnowledgeResult(title=hit.title, content=hit.content) for hit in hits],
    )


@router.post("/check-scam", response_model=CheckScamOut)
async def check_scam(
    body: CheckScamRequest,
    db: DbSession,
    llm: Annotated[LLMClient, Depends(get_scam_llm_client)],
) -> CheckScamOut:
    """How likely what the caller describes is a scam, with the warning to say.

    Every live call gets the warning; only ACTIVE elders' medium and high risks are stored
    (as codes, never the situation), and high risk queues a family alert.
    """
    call = await resolve_call(db, body.session_token)
    assessment = await engine.assess(
        db, llm, body.situation, timeout=get_settings().scam_check_timeout_seconds
    )
    await events.record(db, call, assessment)
    await db.commit()
    return CheckScamOut(
        risk_level=assessment.level,
        scam_type=assessment.scam_type,
        message=warning_message(assessment.level, assessment.scam_type),
    )
