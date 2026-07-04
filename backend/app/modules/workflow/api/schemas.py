from __future__ import annotations

from pydantic import BaseModel


class CreateFlowRequest(BaseModel):
    name: str
    description: str | None = None
    trigger_type: str
    graph: dict


class UpdateFlowRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    graph: dict | None = None


class DryRunFlowRequest(BaseModel):
    """Optional synthetic/sample event to exercise the flow against. When
    omitted, a minimal placeholder event is used. Callers should not send real
    student/candidate PII here — dry-run input is redacted server-side
    regardless, but the endpoint is meant for synthetic test data.
    """

    sample_event: dict | None = None


class ResolveFailedNodeTaskRequest(BaseModel):
    resolution: str = "resolved"  # resolved|dismissed
