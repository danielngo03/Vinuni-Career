"""Org-wide interview/offer export rows (assistant ``export_interviews`` /
``export_offers`` tools).

Thin, RBAC-layered adapters over the SAME org-wide board services the partner
recruiting UI uses (``interview_service.list_org_interviews`` /
``offer_service.list_org_offers``) — no query/tenant/masking rule is duplicated:

- ``applications:export`` is required here first (the narrow file-export grant a
  partner admin hands out, same noun as the applicant export);
- the underlying board service then enforces its own read gate
  (``interviews:read`` / ``offers:create``) and org scoping, so an export can
  never see more than the caller's own board.

Rows are flat + user-safe: candidate display handle, job title, localized
labels. Interview exports NEVER include the meeting link (attendee-only on the
board; a forwarded file must not carry it). Offer salary is included only for a
caller holding the same ``offers:create`` grant that unlocks comp on the board.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.recruitment.application import interview_service, offer_service
from app.modules.recruitment.domain.models import Offer
from app.shared.permissions import Principal, permission_checker

MAX_EXPORT_ROWS = 5000

_INTERVIEW_SCOPES = frozenset({"upcoming", "past", "all"})


def _require_export(principal: Principal) -> None:
    permission_checker.require(
        principal, "applications", "export", resource_org_id=principal.org_id
    )


def _in_range(iso_value: str | None, from_dt: datetime | None, to_dt: datetime | None) -> bool:
    if from_dt is None and to_dt is None:
        return True
    if not iso_value:
        return False
    try:
        dt = datetime.fromisoformat(iso_value)
    except ValueError:
        return False
    if dt.tzinfo is None:
        # Backend timestamps are UTC; SQLite round-trips them naive.
        dt = dt.replace(tzinfo=UTC)
    if from_dt is not None and dt < from_dt:
        return False
    return not (to_dt is not None and dt > to_dt)


async def export_interview_rows(
    session: AsyncSession,
    *,
    principal: Principal,
    scope: str = "all",
    job_id: uuid.UUID | None = None,
    scheduled_from: datetime | None = None,
    scheduled_to: datetime | None = None,
    locale: str = "vi",
) -> list[dict]:
    """Org-wide interview board as flat export rows (capped, meeting-link-free)."""

    _require_export(principal)
    if scope not in _INTERVIEW_SCOPES:
        scope = "all"
    board = await interview_service.list_org_interviews(
        session,
        principal=principal,
        scope=scope,
        job_id=job_id,
        limit=MAX_EXPORT_ROWS,
        offset=0,
        locale=locale,
    )
    rows: list[dict] = []
    for iv in board.get("interviews", []):
        if not _in_range(iv.get("scheduled_at"), scheduled_from, scheduled_to):
            continue
        assignees = ", ".join(
            a.get("display_name", "") for a in (iv.get("assignees") or []) if a
        )
        rows.append(
            {
                "candidate": iv.get("candidate_handle") or "",
                "job": iv.get("job_title") or "",
                "stage": iv.get("stage_name") or "",
                "scheduled_at": iv.get("scheduled_at") or "",
                "mode": iv.get("mode_label") or "",
                "interviewers": assignees,
                "status": iv.get("status_label") or "",
                # NOTE: never the meeting link — attendee-only on the live board.
            }
        )
    return rows


def offer_salary_allowed(principal: Principal) -> bool:
    """Same grant that unlocks comp on the org offer board (``offers:create``)."""

    return permission_checker.can(
        principal, "offers", "create", resource_org_id=principal.org_id
    )


async def export_offer_rows(
    session: AsyncSession,
    *,
    principal: Principal,
    status: str | None = None,
    job_id: uuid.UUID | None = None,
    locale: str = "vi",
) -> tuple[list[dict], bool]:
    """Org-wide offer board as flat export rows. Returns ``(rows, salary_included)``.

    Delegates to ``offer_service.list_org_offers`` (which enforces
    ``offers:create`` + org scope and decrypts comp exactly like the board).
    ``decided_at`` (the candidate's accept/decline moment) is batch-loaded here —
    it is a triage timestamp the board row does not carry.
    """

    _require_export(principal)
    board = await offer_service.list_org_offers(
        session,
        principal=principal,
        scope="all",
        status=status,
        job_id=job_id,
        limit=MAX_EXPORT_ROWS,
        offset=0,
        locale=locale,
    )
    offers = board.get("offers", [])
    salary_included = offer_salary_allowed(principal)

    # Batch-load the candidate-decision timestamp for the exported rows (one
    # query; same-module ORM read — never a cross-module import).
    decided_at: dict[str, str] = {}
    ids = [uuid.UUID(o["id"]) for o in offers if o.get("id")]
    if ids:
        result = (
            await session.execute(
                select(Offer.id, Offer.student_response_at).where(Offer.id.in_(ids))
            )
        ).all()
        decided_at = {
            str(oid): (ts.isoformat() if ts else "") for oid, ts in result
        }

    rows: list[dict] = []
    for o in offers:
        salary = ""
        if salary_included and o.get("salary_amount") is not None:
            salary = (
                f"{o['salary_amount']:,} {o.get('salary_currency') or ''}"
                f"/{o.get('period_label') or ''}"
            )
        rows.append(
            {
                "candidate": o.get("candidate_handle") or "",
                "job": o.get("job_title") or "",
                "position": o.get("position_title") or "",
                "status": o.get("status_label") or "",
                "salary": salary,
                "sent_at": o.get("sent_at") or "",
                "decided_at": decided_at.get(str(o.get("id")), ""),
            }
        )
    return rows, salary_included
