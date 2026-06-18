from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.modules.access.api.identity import get_active_identity
from app.modules.automation.application.workflow_service import (
    create_workflow,
    execute_workflow,
    list_workflows,
    update_workflow,
)
from app.modules.automation.schemas import (
    WorkflowCreate,
    WorkflowExecuteRequest,
    WorkflowExecutionView,
    WorkflowUpdate,
    WorkflowView,
)
from app.platform.database.models import UserOrgRole, WorkflowExecutionLog
from app.platform.database.session import get_db

router = APIRouter()


@router.get("", response_model=list[WorkflowView])
def get_workflows(
    identity: UserOrgRole = Depends(get_active_identity),
    db: Session = Depends(get_db),
) -> list:
    return list_workflows(db, identity.org_id)


@router.post("", response_model=WorkflowView, status_code=201)
def post_workflow(
    payload: WorkflowCreate,
    identity: UserOrgRole = Depends(get_active_identity),
    db: Session = Depends(get_db),
):
    return create_workflow(db, identity.org_id, payload)


@router.put("/{workflow_id}", response_model=WorkflowView)
def put_workflow(
    workflow_id: str,
    payload: WorkflowUpdate,
    identity: UserOrgRole = Depends(get_active_identity),
    db: Session = Depends(get_db),
):
    return update_workflow(db, identity.org_id, workflow_id, payload)


@router.post("/{workflow_id}/execute", response_model=WorkflowExecutionView)
def run_workflow(
    workflow_id: str,
    payload: WorkflowExecuteRequest,
    identity: UserOrgRole = Depends(get_active_identity),
    db: Session = Depends(get_db),
) -> WorkflowExecutionLog:
    return execute_workflow(db, identity.org_id, workflow_id, payload)
