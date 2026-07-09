"""Attachment analysis tool handler (cross-persona).

Thin wrapper over ``attachment_service.analyze_attachment``: the model calls this
with the ``attachment_id`` the user uploaded to the current chat session. The
service is owner + org scoped (404 on a foreign id) and returns a leakage-safe
analysis dict (summary + text preview + optional table/key-values) — never the
storage key, provider/model, or token internals. Available to any authenticated
persona that can attach a file.
"""

from __future__ import annotations

import uuid as _uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.exceptions import AuthRequiredError, ResourceNotFoundError
from app.shared.permissions import Principal


def _parse_uuid(raw: str | None) -> _uuid.UUID | None:
    if not raw:
        return None
    try:
        return _uuid.UUID(str(raw).strip())
    except ValueError:
        return None


async def analyze_attachment(session: AsyncSession, principal: Principal, args: dict) -> dict:
    from app.modules.ai_assistant.application import attachment_service

    if not principal.is_authenticated:
        return {"ok": False, "error": "auth_required"}
    attachment_id = _parse_uuid(args.get("attachment_id"))
    if attachment_id is None:
        return {"ok": False, "error": "attachment_id_required"}

    try:
        result = await attachment_service.analyze_attachment(
            session, principal=principal, attachment_id=attachment_id
        )
    except ResourceNotFoundError:
        return {"ok": False, "error": "not_found"}
    except AuthRequiredError:
        return {"ok": False, "error": "auth_required"}
    except Exception:
        return {"ok": False, "error": "tool_failed"}

    return {"ok": True, **result}
