from __future__ import annotations

from pydantic import BaseModel


class CreateRoutingGraphRequest(BaseModel):
    task_family: str
    graph: dict


class UpdateRoutingGraphRequest(BaseModel):
    graph: dict
