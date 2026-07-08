"""Recipient search for the "new message" composer (Messaging V2).

Honors the permission matrix at the SEARCH layer so the UI can only surface valid
targets — in particular a student can NEVER find another student (institutional
channel; the student↔student block starts at discovery, not just at send).

Returns a flat list of typed targets:
  - ``org``        an organization Page (student/partner → partner/university)
  - ``department`` an internal department channel (staff, own org)
  - ``user``       a colleague (staff, own org)
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.messaging.domain import rules
from app.modules.organization.application import org_reporting_facade
from app.shared.permissions import Principal

_STUDENT_SIDE = frozenset({rules.STUDENT, rules.ALUMNI})


async def _org_targets(
    session: AsyncSession,
    *,
    q: str | None,
    allow_types: set[str],
    exclude_org_id,
    limit: int,
) -> list[dict]:
    result = await org_reporting_facade.search_orgs(
        session, q=q, page=1, page_size=limit
    )
    out: list[dict] = []
    for item in result.get("items", []):
        if item["org_type"] not in allow_types:
            continue
        if item.get("status") != "active":
            continue
        if exclude_org_id is not None and item["id"] == str(exclude_org_id):
            continue
        out.append(
            {
                "kind": "org",
                "org_id": item["id"],
                "slug": item["slug"],
                "display_name": item["display_name"],
                "org_type": item["org_type"],
                "is_verified": item.get("is_verified", False),
            }
        )
    return out


async def search(
    session: AsyncSession,
    *,
    principal: Principal,
    q: str | None = None,
    limit: int = 20,
) -> list[dict]:
    limit = max(1, min(limit, 30))
    persona = principal.persona

    # Students/alumni: may only reach ORGANIZATIONS (partner or university). No
    # student is ever discoverable — the institutional channel starts here.
    if persona in _STUDENT_SIDE:
        return await _org_targets(
            session,
            q=q,
            allow_types={"partner", "university"},
            exclude_org_id=principal.org_id,
            limit=limit,
        )

    targets: list[dict] = []
    if persona in (rules.PARTNER_MEMBER, rules.UNIVERSITY_STAFF) and principal.org_id:
        # Internal: departments + colleagues of the caller's own org.
        depts = await org_reporting_facade.list_departments_brief(
            session, org_id=principal.org_id, q=q, limit=limit
        )
        targets.extend(
            {"kind": "department", "department_id": d["id"], "display_name": d["name"]}
            for d in depts
        )
        members = await org_reporting_facade.list_members_brief(
            session, org_id=principal.org_id, q=q, limit=limit
        )
        targets.extend(
            {
                "kind": "user",
                "user_id": m["user_id"],
                "display_name": m["full_name"],
            }
            for m in members
            if m["user_id"] != str(principal.user_id)
        )
        # Cross-org Page reach: partner → university, university → partner.
        other_type = (
            "university" if persona == rules.PARTNER_MEMBER else "partner"
        )
        targets.extend(
            await _org_targets(
                session,
                q=q,
                allow_types={other_type},
                exclude_org_id=principal.org_id,
                limit=limit,
            )
        )
    return targets[: limit * 2]
