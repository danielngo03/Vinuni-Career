from __future__ import annotations

import pytest
from app.modules.workflow.application import activation_service, flow_service
from app.modules.workflow.application.errors import FlowNotEditableError

from tests.auth_utils import CTX
from tests.org_utils import make_org_with_admin
from tests.workflow_utils import VALID_GRAPH


@pytest.mark.asyncio
async def test_activate_draft_flow_sets_active_and_activated_at(db_session) -> None:
    _user, org, admin = await make_org_with_admin(db_session, org_type="university")
    flow = await flow_service.create_draft_flow(
        db_session,
        principal=admin,
        name="Partner approval",
        description=None,
        trigger_type="system.partner_registered",
        graph=VALID_GRAPH,
        ctx=CTX,
    )

    activated = await activation_service.activate_flow(
        db_session, principal=admin, flow_id=flow.id, ctx=CTX
    )

    assert activated.status == "ACTIVE"
    assert activated.activated_at is not None


@pytest.mark.asyncio
async def test_cannot_update_active_flow_in_place(db_session) -> None:
    _user, org, admin = await make_org_with_admin(db_session, org_type="university")
    flow = await flow_service.create_draft_flow(
        db_session,
        principal=admin,
        name="Partner approval",
        description=None,
        trigger_type="system.partner_registered",
        graph=VALID_GRAPH,
        ctx=CTX,
    )
    await activation_service.activate_flow(db_session, principal=admin, flow_id=flow.id, ctx=CTX)

    with pytest.raises(FlowNotEditableError):
        await flow_service.update_draft_flow(
            db_session,
            principal=admin,
            flow_id=flow.id,
            graph=VALID_GRAPH,
            ctx=CTX,
        )


@pytest.mark.asyncio
async def test_new_draft_version_created_from_active_flow(db_session) -> None:
    _user, org, admin = await make_org_with_admin(db_session, org_type="university")
    flow = await flow_service.create_draft_flow(
        db_session,
        principal=admin,
        name="Partner approval",
        description=None,
        trigger_type="system.partner_registered",
        graph=VALID_GRAPH,
        ctx=CTX,
    )
    await activation_service.activate_flow(db_session, principal=admin, flow_id=flow.id, ctx=CTX)

    new_draft = await activation_service.create_new_draft_version(
        db_session,
        principal=admin,
        flow_id=flow.id,
        graph=VALID_GRAPH,
        ctx=CTX,
    )

    assert new_draft.id != flow.id
    assert new_draft.status == "DRAFT"
    assert new_draft.version == flow.version + 1
