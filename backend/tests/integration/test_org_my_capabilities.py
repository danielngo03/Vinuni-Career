"""``GET /organizations/members/me`` capability map (design spec §6 UI gating).

Covers the wildcard-admin case (everything granted), a scoped non-admin member
(only granted capabilities are ``True``), department scope surfacing, and the
non-org-persona rejection.
"""

from __future__ import annotations

import pytest
from app.modules.organization.application import my_capabilities_service
from app.modules.organization.domain.models import Department, MembershipDepartment
from app.shared.exceptions import PermissionDeniedError

from tests.documents_utils import make_student
from tests.org_utils import add_member, make_org_with_admin


async def test_admin_sees_full_capability_map(db_session) -> None:
    _pu, _porg, admin = await make_org_with_admin(db_session, display_name="Caps Co")
    data = await my_capabilities_service.get_my_capabilities(db_session, principal=admin)

    assert data["is_org_admin"] is True
    assert data["membership_status"] == "active"
    assert data["membership_id"] is not None
    assert "*:*" in data["grants"]
    # Wildcard admin -> every catalog capability resolves True.
    assert all(data["capabilities"].values())
    assert data["capabilities"]["analytics:view_job_metrics"] is True
    assert data["capabilities"]["jobs:create"] is True
    assert data["departments"] == []


async def test_non_admin_capabilities_reflect_only_granted(db_session) -> None:
    _pu, porg, _admin = await make_org_with_admin(db_session)
    _user, _membership, member = await add_member(
        db_session,
        org=porg,
        permissions=[("jobs", "read"), ("applications", "read"), ("analytics", "view_job_metrics")],
    )
    data = await my_capabilities_service.get_my_capabilities(db_session, principal=member)

    assert data["is_org_admin"] is False
    caps = data["capabilities"]
    assert caps["jobs:read"] is True
    assert caps["applications:read"] is True
    assert caps["analytics:view_job_metrics"] is True
    # Not granted -> honest False (nav/action gated off).
    assert caps["jobs:create"] is False
    assert caps["billing:manage"] is False
    assert caps["candidate_identity:download_cv"] is False

    assert "jobs:read" in data["grants"]
    assert data["by_resource"]["applications"] == ["read"]


async def test_department_scope_surfaces(db_session) -> None:
    _pu, porg, _admin = await make_org_with_admin(db_session)
    _user, membership, member = await add_member(
        db_session, org=porg, permissions=[("jobs", "read")]
    )
    dept = Department(org_id=porg.id, name="Engineering Recruiting")
    db_session.add(dept)
    await db_session.flush()
    db_session.add(
        MembershipDepartment(membership_id=membership.id, department_id=dept.id)
    )
    await db_session.commit()

    data = await my_capabilities_service.get_my_capabilities(db_session, principal=member)
    assert data["departments"] == [{"id": str(dept.id), "name": "Engineering Recruiting"}]


async def test_non_org_persona_forbidden(db_session) -> None:
    _su, student = await make_student(db_session)
    with pytest.raises(PermissionDeniedError):
        await my_capabilities_service.get_my_capabilities(db_session, principal=student)
