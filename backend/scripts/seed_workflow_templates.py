"""Seeds the two Phase A workflow templates named in docs/BACKLOG.md B-398:
student verification and partner/employer account approval. Idempotent by
flow name — safe to run repeatedly (local dev bootstrap, CI fixtures).
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.application.context import RequestContext
from app.modules.workflow.application import activation_service, flow_service
from app.modules.workflow.domain.models import WorkflowFlow
from app.shared.permissions import Principal


def _student_verification_graph(assignee_user_id: str) -> dict:
    return {
        "nodes": [
            {"id": "trigger", "type": "trigger", "data": {"trigger_type": "system.student_registered"}},
            {"id": "check_domain", "type": "condition", "data": {"expression": "{{is_university_email}} == True"}},
            {"id": "auto_approve", "type": "action", "data": {"action": "auto_approve"}},
            {
                "id": "manual_review",
                "type": "human_review",
                "data": {"assignee_mode": "person", "assignee_user_id": assignee_user_id, "sla_hours": 48},
            },
            {"id": "end", "type": "end", "data": {}},
        ],
        "edges": [
            {"source": "trigger", "target": "check_domain"},
            {"source": "check_domain", "target": "auto_approve", "condition": "true"},
            {"source": "check_domain", "target": "manual_review", "condition": "false"},
            {"source": "auto_approve", "target": "end"},
            {"source": "manual_review", "target": "end"},
        ],
    }


def _partner_approval_graph(assignee_user_id: str) -> dict:
    return {
        "nodes": [
            {"id": "trigger", "type": "trigger", "data": {"trigger_type": "system.partner_registered"}},
            {
                "id": "manual_review",
                "type": "human_review",
                "data": {"assignee_mode": "person", "assignee_user_id": assignee_user_id, "sla_hours": 72},
            },
            {"id": "send_email", "type": "action", "data": {"action": "notify_decision"}},
            {"id": "end", "type": "end", "data": {}},
        ],
        "edges": [
            {"source": "trigger", "target": "manual_review"},
            {"source": "manual_review", "target": "send_email"},
            {"source": "send_email", "target": "end"},
        ],
    }


async def seed_templates(
    session: AsyncSession, *, principal: Principal, ctx: RequestContext
) -> list[WorkflowFlow]:
    # The seed graphs need a concrete Human Review assignee. A real placeholder
    # department/role would need new organization-module fixtures; instead we
    # use assignee_mode="person" with the seeding principal's own user_id — a
    # university admin is a legitimate first-pass reviewer for seed/demo
    # purposes (see plan Task 9 note).
    assignee_user_id = str(principal.user_id)
    templates = [
        (
            "Student verification",
            "system.student_registered",
            _student_verification_graph(assignee_user_id),
        ),
        (
            "Partner/employer account approval",
            "system.partner_registered",
            _partner_approval_graph(assignee_user_id),
        ),
    ]
    result: list[WorkflowFlow] = []
    for name, trigger_type, graph in templates:
        existing = (
            await session.execute(select(WorkflowFlow).where(WorkflowFlow.name == name))
        ).scalar_one_or_none()
        if existing is not None:
            result.append(existing)
            continue
        flow = await flow_service.create_draft_flow(
            session, principal=principal, name=name, description=None,
            trigger_type=trigger_type, graph=graph, ctx=ctx,
        )
        activated = await activation_service.activate_flow(
            session, principal=principal, flow_id=flow.id, ctx=ctx
        )
        result.append(activated)
    return result
