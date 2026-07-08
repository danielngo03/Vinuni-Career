"""AI-ops debug reads for mock interview (platform superadmin).

Lets platform/AI-ops read interview content to diagnose AI quality problems while
respecting the student privacy boundary agreed with the owner:

- Flagged sessions surface as pseudonymized METADATA (no student identity).
- A specific session's transcript opens REDACTED by default (``redact_pii`` copy);
  the RAW transcript opens only when the caller holds the literal
  ``ai_settings:view_provider_identity`` grant (NOT bypassed by ``is_superadmin``)
  AND the student has opted in (``share_opt_in`` / ``interview_recording``
  consent). Every open — redacted or full — is audited.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.mock_interview.infrastructure import repository as repo
from app.shared.audit import AuditContext, write_audit
from app.shared.exceptions import PermissionDeniedError, ResourceNotFoundError
from app.shared.permissions import Principal

# Literal investigation grant (reused per ADR-0016 §6); wildcard/superadmin do
# NOT satisfy it — mirrors ai_ops identity masking.
_IDENTITY_GRANT = "ai_settings:view_provider_identity"


def _require_superadmin(principal: Principal) -> None:
    if not principal.is_superadmin:
        raise PermissionDeniedError(details={"reason": "superadmin_only"})


async def list_flagged(
    session: AsyncSession, *, principal: Principal, limit: int = 50
) -> list[dict[str, Any]]:
    """Pseudonymized metadata for safety-flagged sessions (no student identity)."""

    _require_superadmin(principal)
    rows = await repo.list_flagged(session, limit=max(1, min(100, limit)))
    return [
        {
            "session_id": str(r.id),
            "job_id": str(r.job_id),
            "modality": r.modality,
            "status": r.status,
            "question_count": r.question_count,
            "share_opt_in": bool(r.share_opt_in),
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]


async def view_transcript(
    session: AsyncSession,
    *,
    principal: Principal,
    ctx: Any | None,
    session_id: uuid.UUID,
) -> dict[str, Any]:
    """Open one session's transcript for AI debugging. Every open is audited.

    Full (raw) content requires the identity grant AND the student's opt-in;
    otherwise the pseudonymized (``redact_pii``) transcript is returned.
    """

    _require_superadmin(principal)
    row = await repo.get_session(session, session_id=session_id, user_id=None)
    if row is None:
        raise ResourceNotFoundError()
    turns = await repo.load_turns(session, session_id=session_id)

    has_grant = _IDENTITY_GRANT in principal.permissions
    full = has_grant and bool(row.share_opt_in)
    mode = "full" if full else "redacted"
    transcript = [
        {
            "seq": t.seq,
            "speaker": t.speaker,
            "text": t.text if full else (t.text_redacted or ""),
        }
        for t in turns
    ]

    await write_audit(
        session,
        action="mock_interview.transcript_viewed",
        resource_type="mock_interview_session",
        resource_id=row.id,
        context=AuditContext(
            actor_id=principal.user_id,
            actor_org_id=principal.org_id,
            ip=getattr(ctx, "ip", None),
            user_agent=getattr(ctx, "user_agent", None),
        ),
        after={
            "mode": mode,
            "opt_in": bool(row.share_opt_in),
            "has_grant": has_grant,
            "flagged": bool(row.flagged),
        },
    )
    await session.commit()

    return {
        "session_id": str(row.id),
        "mode": mode,
        "flagged": bool(row.flagged),
        "modality": row.modality,
        "status": row.status,
        "report": row.report_json,
        "transcript": transcript,
    }
