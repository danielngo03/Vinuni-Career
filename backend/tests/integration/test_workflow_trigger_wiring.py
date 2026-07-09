from __future__ import annotations

import pytest
from app.modules.auth.application import auth_service
from app.modules.users.application import user_service
from app.modules.workflow.application import activation_service, flow_service
from app.modules.workflow.domain.models import WorkflowExecution
from sqlalchemy import select

from tests.auth_utils import CTX, fetch_verification_token
from tests.org_utils import make_org_with_admin
from tests.workflow_utils import VALID_GRAPH


@pytest.mark.asyncio
async def test_verifying_email_triggers_active_student_verification_flow(db_session) -> None:
    _admin_user, org, admin = await make_org_with_admin(db_session, org_type="university")
    flow = await flow_service.create_draft_flow(
        db_session,
        principal=admin,
        name="Student verification",
        description=None,
        trigger_type="system.student_registered",
        graph=VALID_GRAPH,
        ctx=CTX,
    )
    await activation_service.activate_flow(db_session, principal=admin, flow_id=flow.id, ctx=CTX)

    await auth_service.register(
        db_session,
        email="new.student@example.com",
        password="Str0ngPassw0rd!",
        full_name="New Student",
        ctx=CTX,
    )
    new_user = await user_service.get_by_email(db_session, "new.student@example.com")
    assert new_user is not None
    token = await fetch_verification_token(db_session, new_user.id)
    await auth_service.verify_email(db_session, token=token, ctx=CTX)

    executions = (await db_session.execute(select(WorkflowExecution))).scalars().all()
    assert any(e.flow_id == flow.id for e in executions)
