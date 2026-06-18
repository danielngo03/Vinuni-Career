from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.automation.schemas import WorkflowCreate, WorkflowExecuteRequest, WorkflowUpdate
from app.platform.database.models import AutomationWorkflow, WorkflowExecutionLog
from app.shared.errors import AppError, ErrorCode


def list_workflows(db: Session, org_id: str) -> list[AutomationWorkflow]:
    return list(
        db.scalars(
            select(AutomationWorkflow)
            .where(AutomationWorkflow.org_id == org_id)
            .order_by(AutomationWorkflow.created_at.desc())
        )
    )


def create_workflow(db: Session, org_id: str, payload: WorkflowCreate) -> AutomationWorkflow:
    workflow = AutomationWorkflow(
        org_id=org_id,
        name=payload.name,
        trigger_event=payload.trigger_event,
        graph_data=payload.graph_data.model_dump(),
        is_active=payload.is_active,
    )
    db.add(workflow)
    db.commit()
    db.refresh(workflow)
    return workflow


def update_workflow(
    db: Session,
    org_id: str,
    workflow_id: str,
    payload: WorkflowUpdate,
) -> AutomationWorkflow:
    workflow = _get_workflow(db, org_id, workflow_id)
    changes = payload.model_dump(exclude_unset=True)
    if "graph_data" in changes and payload.graph_data:
        changes["graph_data"] = payload.graph_data.model_dump()
    for key, value in changes.items():
        setattr(workflow, key, value)
    db.commit()
    db.refresh(workflow)
    return workflow


def execute_workflow(
    db: Session,
    org_id: str,
    workflow_id: str,
    payload: WorkflowExecuteRequest,
) -> WorkflowExecutionLog:
    workflow = _get_workflow(db, org_id, workflow_id)
    if not workflow.is_active:
        raise AppError(code=ErrorCode.CONFLICT, message="Workflow is disabled", status_code=409)
    nodes = workflow.graph_data.get("nodes", [])
    execution = WorkflowExecutionLog(
        workflow_id=workflow.id,
        target_id=payload.target_id,
        status="SUCCEEDED",
        execution_trace={
            "trigger": workflow.trigger_event,
            "evaluated_nodes": [node.get("id") for node in nodes],
            "context": payload.context,
        },
    )
    db.add(execution)
    db.commit()
    db.refresh(execution)
    return execution


def _get_workflow(db: Session, org_id: str, workflow_id: str) -> AutomationWorkflow:
    workflow = db.get(AutomationWorkflow, workflow_id)
    if not workflow or workflow.org_id != org_id:
        raise AppError(code=ErrorCode.NOT_FOUND, message="Workflow not found", status_code=404)
    return workflow
