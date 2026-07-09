"""Retrieval of assistant-generated download files (RBAC + expiry).

The bytes/storage are never exposed directly — the client only ever gets the
``/ai/chat/exports/{id}`` URL, and this service re-checks ownership + expiry on
every download. A file belongs to the user who generated it (owner-only), which
is stricter than org scope and matches how the recruiter requested it.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.ai_assistant.domain.models import ChatExportFile
from app.shared.exceptions import AuthRequiredError, ResourceNotFoundError
from app.shared.permissions import Principal


async def fetch_export(
    session: AsyncSession, principal: Principal, export_id: uuid.UUID
) -> ChatExportFile:
    """Load an export the caller owns; raise if missing, foreign, or expired."""
    if not principal.is_authenticated:
        raise AuthRequiredError()
    row = await session.get(ChatExportFile, export_id)
    if row is None:
        raise ResourceNotFoundError()
    if not principal.is_superadmin and row.user_id != principal.user_id:
        # Do not disclose existence of another user's export.
        raise ResourceNotFoundError()
    if row.expires_at is not None and row.expires_at < datetime.now(UTC):
        raise ResourceNotFoundError()
    return row
