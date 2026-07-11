from __future__ import annotations

import pytest
from app.modules.workflow.application import flow_service
from app.modules.workflow.application.errors import InvalidGraphError
from app.shared.exceptions import PermissionDeniedError

from tests.auth_utils import CTX
from tests.org_utils import add_member, make_org_with_admin
from tests.workflow_utils import VALID_GRAPH


@pytest.mark.asyncio
async def test_admin_can_create_and_read_draft_flow(db_session) -> None:
    _user, org, admin = await make_org_with_admin(db_session, org_type="university")

    flow = await flow_service.create_draft_flow(
        db_session,
        principal=admin,
        name="Student verification",
        description="Auto/manual verification of new student accounts",
        trigger_type="system.student_registered",
        graph=VALID_GRAPH,
        ctx=CTX,
    )

    assert flow.status == "DRAFT"
    assert flow.version == 1

    fetched = await flow_service.get_flow(db_session, principal=admin, flow_id=flow.id)
    assert fetched.id == flow.id


@pytest.mark.asyncio
async def test_create_flow_rejects_invalid_graph(db_session) -> None:
    _user, org, admin = await make_org_with_admin(db_session, org_type="university")

    with pytest.raises(InvalidGraphError):
        await flow_service.create_draft_flow(
            db_session,
            principal=admin,
            name="Broken",
            description=None,
            trigger_type="system.student_registered",
            graph={"nodes": [], "edges": []},
            ctx=CTX,
        )


@pytest.mark.asyncio
async def test_member_without_workflow_create_permission_is_denied(db_session) -> None:
    _user, org, admin = await make_org_with_admin(db_session, org_type="university")
    _member_user, _membership, member = await add_member(
        db_session, org=org, permissions=[("workflow", "read")]
    )

    with pytest.raises(PermissionDeniedError):
        await flow_service.create_draft_flow(
            db_session,
            principal=member,
            name="Student verification",
            description=None,
            trigger_type="system.student_registered",
            graph=VALID_GRAPH,
            ctx=CTX,
        )
