from __future__ import annotations

import hashlib
import hmac

from fastapi import APIRouter, Header, Request

from app.api.exceptions import AppError, ErrorCode
from app.core.config import settings
from app.schemas.webhooks import AcademicRecordEvent, WebhookAck

router = APIRouter()


@router.post("/academic-records", response_model=WebhookAck, status_code=202)
async def academic_records_webhook(
    request: Request,
    x_signature: str | None = Header(default=None, alias="X-Signature"),
) -> WebhookAck:
    body = await request.body()
    _verify_signature(body, x_signature)
    AcademicRecordEvent.model_validate_json(body)
    return WebhookAck(accepted=True, event_type="academic_records")


def _verify_signature(body: bytes, signature: str | None) -> None:
    if not settings.webhook_shared_secret:
        return
    if not signature:
        raise AppError(
            code=ErrorCode.UNAUTHORIZED,
            message="Missing webhook signature",
            status_code=401,
        )
    expected = hmac.new(
        settings.webhook_shared_secret.encode("utf-8"),
        body,
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(signature, expected):
        raise AppError(
            code=ErrorCode.UNAUTHORIZED,
            message="Invalid webhook signature",
            status_code=401,
        )
