from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession
from svix.webhooks import Webhook, WebhookVerificationError

from app.core.config import get_settings
from app.core.db import get_db
from app.core.errors import AppError
from app.schemas.clerk import ClerkEvent
from app.services.identity import users

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


def get_clerk_webhook() -> Webhook:
    secret = get_settings().clerk_webhook_secret
    if not secret:
        raise AppError(500, "webhook_not_configured", "Clerk webhook is not configured")
    return Webhook(secret)


@router.post("/clerk")
async def clerk_webhook(
    request: Request,
    webhook: Annotated[Webhook, Depends(get_clerk_webhook)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, bool]:
    body = await request.body()
    try:
        # svix 2.x only verifies (returns None); the body is parsed separately.
        webhook.verify(body, dict(request.headers))
        event = ClerkEvent.model_validate_json(body)
    except WebhookVerificationError as exc:
        raise AppError(400, "invalid_signature", "Webhook signature is invalid") from exc
    except ValidationError as exc:
        raise AppError(400, "invalid_payload", "Webhook payload is invalid") from exc

    try:
        await users.apply_clerk_event(db, event)
    except ValidationError as exc:
        raise AppError(400, "invalid_payload", "Webhook payload is invalid") from exc
    await db.commit()
    return {"received": True}
