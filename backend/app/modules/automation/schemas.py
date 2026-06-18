from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class WorkflowGraph(BaseModel):
    nodes: list[dict[str, Any]] = Field(default_factory=list, max_length=100)
    edges: list[dict[str, Any]] = Field(default_factory=list, max_length=200)

    @model_validator(mode="after")
    def validate_graph(self) -> WorkflowGraph:
        node_ids = {str(node.get("id")) for node in self.nodes if node.get("id")}
        if len(node_ids) != len(self.nodes):
            raise ValueError("Every workflow node must have a unique id")
        for edge in self.edges:
            if str(edge.get("source")) not in node_ids or str(edge.get("target")) not in node_ids:
                raise ValueError("Workflow edge references an unknown node")
        return self


class WorkflowCreate(BaseModel):
    name: str = Field(min_length=3, max_length=255)
    trigger_event: str = Field(min_length=3, max_length=120)
    graph_data: WorkflowGraph
    is_active: bool = True


class WorkflowUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=3, max_length=255)
    trigger_event: str | None = Field(default=None, min_length=3, max_length=120)
    graph_data: WorkflowGraph | None = None
    is_active: bool | None = None


class WorkflowView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    org_id: str
    name: str
    trigger_event: str
    graph_data: dict[str, Any]
    is_active: bool
    created_at: datetime
    updated_at: datetime | None


class WorkflowExecuteRequest(BaseModel):
    target_id: str | None = None
    context: dict[str, Any] = Field(default_factory=dict)


class WorkflowExecutionView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    workflow_id: str
    target_id: str | None
    status: str
    execution_trace: dict[str, Any]
    executed_at: datetime


class AcademicRecordEvent(BaseModel):
    student_code: str = Field(min_length=1, max_length=80)
    org_id: str
    records: list[dict[str, Any]]


class WebhookAck(BaseModel):
    accepted: bool
    event_type: str
