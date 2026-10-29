from fastapi import APIRouter, Depends

from app.core.db import DbSession
from app.core.dograh_auth import require_dograh_key
from app.schemas.dograh import PreCallRequest, PreCallResponse
from app.services.identity import pre_call

router = APIRouter(prefix="/hooks", tags=["dograh"], dependencies=[Depends(require_dograh_key)])


@router.post("/pre-call", response_model=PreCallResponse, response_model_exclude_none=True)
async def pre_call_hook(body: PreCallRequest, db: DbSession) -> PreCallResponse:
    """Dograh calls this before the agent speaks; the response merges into `initial_context`."""
    context = await pre_call.build_context(db, body.call_inbound)
    await db.commit()
    return PreCallResponse(initial_context=context)
