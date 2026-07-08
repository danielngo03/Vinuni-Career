# Workflow Engine Phase A (Account Approval Backend) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the backend execution engine for the Visual Workflow Builder (E23) — flow/execution persistence, a graph interpreter with Trigger/Condition/Human Review/Action/Delay/End node types, trigger dispatch from real account-registration events, and two seeded templates (student verification, partner/employer approval) — with no drag-and-drop canvas yet (that's Phase B, a separate plan).

**Architecture:** New `backend/app/modules/workflow/` module, 4-layer shape (`api/application/domain/infrastructure`) mirroring `backend/app/modules/recruitment/`. Flows are versioned JSONB graphs (`workflow_flows`); each trigger produces a `workflow_executions` row with a per-node `node_logs` audit trail. The interpreter (`execute_flow`) runs as a plain async function callable inline (tests, local dev) and is also registered as a Celery task on the existing `app.modules.automation.workers.celery_app.celery_app` instance for the deferred production path — mirroring how every other background job in this codebase is dual-pathed (see `app/core/worker.py`). Trigger dispatch hooks into `auth_service.verify_email` (student_registered) and `partner_registration_service.register_partner` (partner_registered) via a public `workflow.application.trigger_service.dispatch_trigger()` call, the same cross-module pattern already used for `enqueue_notification`.

**Tech Stack:** FastAPI async, SQLAlchemy 2.x async, Alembic, Pydantic v2, pytest + pytest-asyncio, SQLite (aiosqlite) for tests per `backend/tests/conftest.py`.

## Global Constraints

- RBAC must be enforced in the application/service layer, not only routers (`.claude/rules/backend.md`).
- Every write action must create an audit row via `app.shared.audit.write_audit` (`.claude/rules/backend.md`).
- No raw enum codes or internal AI/provider details in end-user responses.
- No direct cross-module implementation imports — only public `application` service functions of other modules may be imported (`.claude/rules/backend.md`).
- Workflow graphs are DAG-only, versioned, and an ACTIVE version can never be edited in place — editing creates a new DRAFT version (`.claude/rules/realtime.md`, `docs/API_CONTRACTS.md` `/workflows` contract).
- Max 100 concurrent executions per flow; excess queues FIFO up to 10,000 (`docs/BUSINESS_LOGIC.md` §16.1).
- Each `(trigger_event, flow_id)` pair produces at most one execution — idempotent (`docs/BUSINESS_LOGIC.md` §16.1).
- Human Review node SLA breach escalates via email + in-app + activity feed (`docs/BUSINESS_LOGIC.md` §16.1); `assignee_mode` is `"person"` (named `assignee_user_id`) or `"queue"` (`assignee_department_id`), never a hardcoded role string (`CLAUDE.md` "do not hardcode university staff roles").
- New permission strings must be added to `PERMISSION_CATALOG` in `backend/app/modules/organization/domain/catalog.py` — this is a required code change, not just a migration (confirmed via codebase investigation).
- Migrations must have both `upgrade()` and `downgrade()`, chained off the current head `down_revision = "0047_ai_provider_encrypted_keys"`.
- Tests must not require a live Postgres/Redis/Celery worker — drive `execute_flow` and `dispatch_trigger` directly as async functions (per `.claude/rules/testing.md` order-independence and `docs/LOCAL_DEV_STACK.md` inline-worker default).
- `DEBUG` env var must be boolean when running tests; if the parent shell has a non-boolean `DEBUG`, prefix test commands with `DEBUG=false`.

---

### Task 1: Permission catalog entries + Alembic migration for `workflow_flows` / `workflow_executions`

**Files:**
- Modify: `backend/app/modules/organization/domain/catalog.py`
- Create: `backend/alembic/versions/0048_workflow_engine.py`
- Test: `backend/tests/integration/test_workflow_migration.py`

**Interfaces:**
- Produces: DB tables `workflow_flows(id, name, description, trigger_type, graph, status, version, created_by, created_at, activated_at)` and `workflow_executions(id, flow_id, trigger_event, status, started_at, finished_at, node_logs)`; catalog resources `"workflow": frozenset({"create", "activate", "read", "update"})`.

- [ ] **Step 1: Add the `workflow` permission resource to the catalog**

Open `backend/app/modules/organization/domain/catalog.py`, find `PERMISSION_CATALOG` and add an entry (keep alphabetical if the existing dict is ordered that way):

```python
    "workflow": frozenset({"create", "read", "update", "activate"}),
```

- [ ] **Step 2: Write a failing test asserting the catalog accepts the new permission**

```python
# backend/tests/integration/test_workflow_migration.py
from __future__ import annotations

from app.modules.organization.domain.catalog import is_catalog_permission


def test_workflow_permissions_registered() -> None:
    assert is_catalog_permission("workflow", "create")
    assert is_catalog_permission("workflow", "activate")
    assert not is_catalog_permission("workflow", "delete")
```

- [ ] **Step 3: Run the test to verify it currently fails (catalog not yet updated in a fresh checkout) or passes if Step 1 already applied — then generate the migration**

Run: `cd backend && DEBUG=false uv run pytest tests/integration/test_workflow_migration.py -v`
Expected: PASS (Step 1 already applied the catalog change). If it fails with `AssertionError`, re-check Step 1 was saved.

Then scaffold the migration file:

Run: `cd backend && uv run alembic revision -m "workflow engine tables"`

- [ ] **Step 4: Replace the generated migration body**

Rename the generated file to `backend/alembic/versions/0048_workflow_engine.py` and set its content to:

```python
"""workflow engine tables

Revision ID: 0048_workflow_engine
Revises: 0047_ai_provider_encrypted_keys
Create Date: 2026-07-02
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0048_workflow_engine"
down_revision = "0047_ai_provider_encrypted_keys"
branch_labels = None
depends_on = None

_JSON = sa.JSON().with_variant(JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        "workflow_flows",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("trigger_type", sa.String(length=60), nullable=False),
        sa.Column("graph", _JSON, nullable=False),
        sa.Column(
            "status", sa.String(length=20), nullable=False, server_default="DRAFT"
        ),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_workflow_flows_trigger_status",
        "workflow_flows",
        ["trigger_type", "status"],
    )

    op.create_table(
        "workflow_executions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "flow_id",
            sa.Uuid(),
            sa.ForeignKey("workflow_flows.id"),
            nullable=False,
        ),
        sa.Column("trigger_event", _JSON, nullable=False),
        sa.Column("idempotency_key", sa.String(length=200), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "node_logs", _JSON, nullable=False, server_default=sa.text("'[]'")
        ),
    )
    op.create_index(
        "ix_workflow_executions_idempotency",
        "workflow_executions",
        ["flow_id", "idempotency_key"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_workflow_executions_idempotency", table_name="workflow_executions")
    op.drop_table("workflow_executions")
    op.drop_index("ix_workflow_flows_trigger_status", table_name="workflow_flows")
    op.drop_table("workflow_flows")
```

- [ ] **Step 5: Run the migration up and down against the local dev DB**

Run: `cd backend && uv run alembic upgrade head`
Expected: no errors, ends at revision `0048_workflow_engine`.

Run: `cd backend && uv run alembic downgrade -1 && uv run alembic upgrade head`
Expected: downgrade then upgrade both succeed with no errors.

- [ ] **Step 6: Commit**

```bash
cd backend && git add app/modules/organization/domain/catalog.py alembic/versions/0048_workflow_engine.py tests/integration/test_workflow_migration.py
git commit -m "feat(workflow): add workflow_flows/workflow_executions tables and workflow permission catalog entries"
```

---

### Task 2: Domain models, enums, and `FlowContext`

**Files:**
- Create: `backend/app/modules/workflow/__init__.py`
- Create: `backend/app/modules/workflow/domain/__init__.py`
- Create: `backend/app/modules/workflow/domain/models.py`
- Create: `backend/app/modules/workflow/domain/graph.py`
- Test: `backend/tests/unit/test_workflow_domain.py`

**Interfaces:**
- Consumes: `app.shared.models.Base`, `JsonType` (Task 1's tables).
- Produces: ORM classes `WorkflowFlow`, `WorkflowExecution`; enums `TriggerType`, `NodeType`, `FlowStatus`, `ExecutionStatus`; dataclass `FlowContext(trigger: dict, variables: dict)` with `.interpolate(template: str) -> str` and `.merge(output: dict) -> None`.

- [ ] **Step 1: Write failing unit tests for `FlowContext` interpolation**

```python
# backend/tests/unit/test_workflow_domain.py
from __future__ import annotations

from app.modules.workflow.domain.graph import FlowContext


def test_flow_context_interpolates_trigger_and_variables() -> None:
    ctx = FlowContext(trigger={"user_id": "u1"}, variables={"fraud_score": 0.82})
    assert ctx.interpolate("{{fraud_score}} > 0.70") == "0.82 > 0.70"
    assert ctx.interpolate("user={{user_id}}") == "user=u1"


def test_flow_context_merge_accumulates_variables() -> None:
    ctx = FlowContext(trigger={}, variables={"a": 1})
    ctx.merge({"b": 2})
    assert ctx.variables == {"a": 1, "b": 2}


def test_flow_context_interpolate_missing_key_raises() -> None:
    ctx = FlowContext(trigger={}, variables={})
    import pytest

    with pytest.raises(KeyError):
        ctx.interpolate("{{missing}}")
```

- [ ] **Step 2: Run to verify failure**

Run: `cd backend && DEBUG=false uv run pytest tests/unit/test_workflow_domain.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.modules.workflow'`

- [ ] **Step 3: Create the module scaffolding and domain code**

```python
# backend/app/modules/workflow/__init__.py
```

```python
# backend/app/modules/workflow/domain/__init__.py
```

```python
# backend/app/modules/workflow/domain/graph.py
"""Pure graph/context concepts for the workflow engine: no I/O, no ORM."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum

_VAR_PATTERN = re.compile(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}")


class TriggerType(StrEnum):
    STUDENT_REGISTERED = "system.student_registered"
    APPLICATION_SUBMITTED = "system.application_submitted"
    PAYMENT_RECEIVED = "system.payment_received"
    FILE_UPLOADED = "system.file_uploaded"
    PARTNER_REGISTERED = "system.partner_registered"
    SCHEDULER_CRON = "scheduler.cron"


class NodeType(StrEnum):
    TRIGGER = "trigger"
    CONDITION = "condition"
    AI_PROCESS = "ai_process"
    HUMAN_REVIEW = "human_review"
    ACTION = "action"
    DELAY = "delay"
    END = "end"


class FlowStatus(StrEnum):
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    ARCHIVED = "ARCHIVED"


class ExecutionStatus(StrEnum):
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


@dataclass(slots=True)
class FlowContext:
    """Variables available to node expressions, accumulated across a run.

    ``trigger`` is the original event payload (read-only in practice, never
    mutated); ``variables`` accumulates each node's declared outputs so later
    nodes can reference ``{{some_output}}`` per docs/BUSINESS_LOGIC.md §16.2.
    """

    trigger: dict
    variables: dict = field(default_factory=dict)

    def _lookup(self, key: str) -> str:
        if key in self.variables:
            return str(self.variables[key])
        if key in self.trigger:
            return str(self.trigger[key])
        raise KeyError(f"unknown flow variable: {key}")

    def interpolate(self, template: str) -> str:
        return _VAR_PATTERN.sub(lambda m: self._lookup(m.group(1)), template)

    def merge(self, output: dict) -> None:
        self.variables.update(output)
```

```python
# backend/app/modules/workflow/domain/models.py
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.models import Base, JsonType


class WorkflowFlow(Base):
    __tablename__ = "workflow_flows"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text(), default=None)
    trigger_type: Mapped[str] = mapped_column(String(60))
    graph: Mapped[dict] = mapped_column(JsonType)
    status: Mapped[str] = mapped_column(String(20), default="DRAFT")
    version: Mapped[int] = mapped_column(default=1)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime]
    activated_at: Mapped[datetime | None] = mapped_column(default=None)


class WorkflowExecution(Base):
    __tablename__ = "workflow_executions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    flow_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workflow_flows.id"))
    trigger_event: Mapped[dict] = mapped_column(JsonType)
    idempotency_key: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(20))
    started_at: Mapped[datetime]
    finished_at: Mapped[datetime | None] = mapped_column(default=None)
    node_logs: Mapped[list] = mapped_column(JsonType, default=list)
```

- [ ] **Step 4: Register the new models with the app's model importer**

Run: `grep -rn "import_all_models\|recruitment.domain.models" backend/tests/conftest.py backend/app/core/*.py 2>/dev/null`

Add `workflow.domain.models` to whatever central model-registration list that search surfaces (mirror how `recruitment.domain.models` is already registered), so `create_all`/Alembic autodiscovery picks up the two new tables in tests.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd backend && DEBUG=false uv run pytest tests/unit/test_workflow_domain.py -v`
Expected: 3 passed

- [ ] **Step 6: Commit**

```bash
cd backend && git add app/modules/workflow/ tests/unit/test_workflow_domain.py
git commit -m "feat(workflow): add domain models, enums, and FlowContext"
```

---

### Task 3: Graph validation — DAG/cycle detection and node schema (incl. Human Review `assignee_mode`)

**Files:**
- Create: `backend/app/modules/workflow/domain/validation.py`
- Test: `backend/tests/unit/test_workflow_validation.py`

**Interfaces:**
- Consumes: `NodeType` (Task 2).
- Produces: `validate_graph(graph: dict) -> list[str]` (returns error messages, empty list = valid), `GraphValidationError(errors: list[str])` (raised by the service layer in Task 4).

Graph JSON shape (React Flow node/edge format, matches `docs/ARCHITECTURE.md`):
```json
{
  "nodes": [
    {"id": "n1", "type": "trigger", "data": {"trigger_type": "system.student_registered"}},
    {"id": "n2", "type": "condition", "data": {"expression": "{{fraud_score}} > 0.70"}},
    {"id": "n3", "type": "human_review", "data": {"assignee_mode": "person", "assignee_user_id": "...", "sla_hours": 24}},
    {"id": "n4", "type": "action", "data": {"action": "auto_approve"}},
    {"id": "n5", "type": "end", "data": {}}
  ],
  "edges": [
    {"source": "n1", "target": "n2"},
    {"source": "n2", "target": "n3", "condition": "true"},
    {"source": "n2", "target": "n4", "condition": "false"},
    {"source": "n3", "target": "n5"},
    {"source": "n4", "target": "n5"}
  ]
}
```

- [ ] **Step 1: Write failing tests**

```python
# backend/tests/unit/test_workflow_validation.py
from __future__ import annotations

from app.modules.workflow.domain.validation import validate_graph

VALID_GRAPH = {
    "nodes": [
        {"id": "n1", "type": "trigger", "data": {"trigger_type": "system.student_registered"}},
        {"id": "n2", "type": "human_review", "data": {"assignee_mode": "person", "assignee_user_id": "11111111-1111-1111-1111-111111111111", "sla_hours": 24}},
        {"id": "n3", "type": "end", "data": {}},
    ],
    "edges": [
        {"source": "n1", "target": "n2"},
        {"source": "n2", "target": "n3"},
    ],
}


def test_valid_graph_has_no_errors() -> None:
    assert validate_graph(VALID_GRAPH) == []


def test_cycle_is_rejected() -> None:
    graph = {
        "nodes": VALID_GRAPH["nodes"],
        "edges": [
            {"source": "n1", "target": "n2"},
            {"source": "n2", "target": "n1"},
        ],
    }
    errors = validate_graph(graph)
    assert any("cycle" in e for e in errors)


def test_missing_trigger_node_is_rejected() -> None:
    graph = {"nodes": [{"id": "n1", "type": "end", "data": {}}], "edges": []}
    errors = validate_graph(graph)
    assert any("exactly one trigger node" in e for e in errors)


def test_human_review_requires_assignee_fields() -> None:
    graph = {
        "nodes": [
            {"id": "n1", "type": "trigger", "data": {"trigger_type": "system.student_registered"}},
            {"id": "n2", "type": "human_review", "data": {"assignee_mode": "person"}},
        ],
        "edges": [{"source": "n1", "target": "n2"}],
    }
    errors = validate_graph(graph)
    assert any("assignee_user_id" in e for e in errors)


def test_human_review_queue_mode_requires_department() -> None:
    graph = {
        "nodes": [
            {"id": "n1", "type": "trigger", "data": {"trigger_type": "system.student_registered"}},
            {"id": "n2", "type": "human_review", "data": {"assignee_mode": "queue"}},
        ],
        "edges": [{"source": "n1", "target": "n2"}],
    }
    errors = validate_graph(graph)
    assert any("assignee_department_id" in e for e in errors)


def test_orphan_node_is_rejected() -> None:
    graph = {
        "nodes": VALID_GRAPH["nodes"] + [{"id": "n4", "type": "end", "data": {}}],
        "edges": VALID_GRAPH["edges"],
    }
    errors = validate_graph(graph)
    assert any("orphan" in e for e in errors)
```

- [ ] **Step 2: Run to verify failure**

Run: `cd backend && DEBUG=false uv run pytest tests/unit/test_workflow_validation.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement validation**

```python
# backend/app/modules/workflow/domain/validation.py
"""Structural validation for a workflow graph before it can be saved as DRAFT
or promoted to ACTIVE. Pure function, no I/O.
"""

from __future__ import annotations

from app.modules.workflow.domain.graph import NodeType

_VALID_TYPES = {t.value for t in NodeType}
_VALID_ASSIGNEE_MODES = {"person", "queue"}


def validate_graph(graph: dict) -> list[str]:
    errors: list[str] = []
    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])
    node_ids = {n["id"] for n in nodes}

    trigger_nodes = [n for n in nodes if n.get("type") == NodeType.TRIGGER.value]
    if len(trigger_nodes) != 1:
        errors.append("graph must contain exactly one trigger node")

    for node in nodes:
        node_type = node.get("type")
        if node_type not in _VALID_TYPES:
            errors.append(f"node {node.get('id')} has unknown type {node_type!r}")
            continue
        if node_type == NodeType.HUMAN_REVIEW.value:
            errors.extend(_validate_human_review(node))

    for edge in edges:
        if edge.get("source") not in node_ids or edge.get("target") not in node_ids:
            errors.append(f"edge references unknown node: {edge}")

    reachable = _reachable_from_trigger(nodes, edges)
    for node in nodes:
        if node["id"] not in reachable:
            errors.append(f"orphan node not reachable from trigger: {node['id']}")

    if _has_cycle(node_ids, edges):
        errors.append("graph contains a cycle; workflow graphs must be a DAG")

    return errors


def _validate_human_review(node: dict) -> list[str]:
    errors: list[str] = []
    data = node.get("data", {})
    mode = data.get("assignee_mode")
    if mode not in _VALID_ASSIGNEE_MODES:
        errors.append(
            f"node {node['id']}: assignee_mode must be one of {_VALID_ASSIGNEE_MODES}"
        )
        return errors
    if mode == "person" and not data.get("assignee_user_id"):
        errors.append(f"node {node['id']}: assignee_mode=person requires assignee_user_id")
    if mode == "queue" and not data.get("assignee_department_id"):
        errors.append(
            f"node {node['id']}: assignee_mode=queue requires assignee_department_id"
        )
    return errors


def _reachable_from_trigger(nodes: list[dict], edges: list[dict]) -> set[str]:
    trigger = next((n["id"] for n in nodes if n.get("type") == NodeType.TRIGGER.value), None)
    if trigger is None:
        return set()
    adjacency: dict[str, list[str]] = {}
    for edge in edges:
        adjacency.setdefault(edge["source"], []).append(edge["target"])
    seen: set[str] = set()
    stack = [trigger]
    while stack:
        current = stack.pop()
        if current in seen:
            continue
        seen.add(current)
        stack.extend(adjacency.get(current, []))
    return seen


def _has_cycle(node_ids: set[str], edges: list[dict]) -> bool:
    adjacency: dict[str, list[str]] = {n: [] for n in node_ids}
    for edge in edges:
        if edge.get("source") in adjacency:
            adjacency[edge["source"]].append(edge.get("target"))

    WHITE, GRAY, BLACK = 0, 1, 2
    color = dict.fromkeys(node_ids, WHITE)

    def dfs(node: str) -> bool:
        color[node] = GRAY
        for neighbor in adjacency.get(node, []):
            if neighbor not in color:
                continue
            if color[neighbor] == GRAY:
                return True
            if color[neighbor] == WHITE and dfs(neighbor):
                return True
        color[node] = BLACK
        return False

    return any(color[n] == WHITE and dfs(n) for n in node_ids)


class GraphValidationError(Exception):
    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__("; ".join(errors))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && DEBUG=false uv run pytest tests/unit/test_workflow_validation.py -v`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
cd backend && git add app/modules/workflow/domain/validation.py tests/unit/test_workflow_validation.py
git commit -m "feat(workflow): add DAG/cycle validation and Human Review assignee_mode schema check"
```

---

### Task 4: Flow CRUD application service (`workflow:create`/`workflow:read`/`workflow:update`)

**Files:**
- Create: `backend/app/modules/workflow/application/__init__.py`
- Create: `backend/app/modules/workflow/application/errors.py`
- Create: `backend/app/modules/workflow/application/flow_service.py`
- Create: `backend/tests/workflow_utils.py`
- Test: `backend/tests/integration/test_workflow_flow_service.py`

**Interfaces:**
- Consumes: `WorkflowFlow` (Task 2), `validate_graph`/`GraphValidationError` (Task 3), `app.shared.permissions.permission_checker`, `app.shared.audit.write_audit`/`AuditContext`, `app.modules.auth.application.context.RequestContext`.
- Produces: `create_draft_flow(session, *, principal, name, description, trigger_type, graph, ctx) -> WorkflowFlow`, `update_draft_flow(session, *, principal, flow_id, name=None, description=None, graph=None, ctx) -> WorkflowFlow`, `get_flow(session, *, principal, flow_id) -> WorkflowFlow`, `list_flows(session, *, principal, status=None) -> list[WorkflowFlow]`.

- [ ] **Step 1: Add the test helper module**

```python
# backend/tests/workflow_utils.py
from __future__ import annotations

VALID_GRAPH = {
    "nodes": [
        {"id": "n1", "type": "trigger", "data": {"trigger_type": "system.student_registered"}},
        {
            "id": "n2",
            "type": "human_review",
            "data": {
                "assignee_mode": "queue",
                "assignee_department_id": "22222222-2222-2222-2222-222222222222",
                "sla_hours": 24,
            },
        },
        {"id": "n3", "type": "end", "data": {}},
    ],
    "edges": [
        {"source": "n1", "target": "n2"},
        {"source": "n2", "target": "n3"},
    ],
}
```

- [ ] **Step 2: Write failing integration tests**

```python
# backend/tests/integration/test_workflow_flow_service.py
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
    _member_user, member = await add_member(
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
```

Run: `grep -n "async def add_member" -A 20 backend/tests/org_utils.py` to confirm `add_member`'s exact return shape and adjust the test's unpacking (`_member_user, member`) to match what it actually returns before proceeding.

- [ ] **Step 3: Run to verify failure**

Run: `cd backend && DEBUG=false uv run pytest tests/integration/test_workflow_flow_service.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.modules.workflow.application'`

- [ ] **Step 4: Implement errors and the service**

```python
# backend/app/modules/workflow/application/__init__.py
```

```python
# backend/app/modules/workflow/application/errors.py
from __future__ import annotations

from app.shared.exceptions import ConflictError, ValidationFailedError


class InvalidGraphError(ValidationFailedError):
    message = "Sơ đồ quy trình không hợp lệ."

    def __init__(self, errors: list[str]) -> None:
        super().__init__(self.message, details={"reason": "invalid_graph", "errors": errors})


class FlowNotEditableError(ConflictError):
    message = "Chỉ có thể chỉnh sửa quy trình ở trạng thái nháp."

    def __init__(self) -> None:
        super().__init__(self.message, details={"reason": "not_editable"})
```

```python
# backend/app/modules/workflow/application/flow_service.py
"""Draft flow CRUD: RBAC + graph validation + audit. Activation lives in
``activation_service`` (Task 5) since it has different permission and
immutability rules.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.application.context import RequestContext
from app.modules.workflow.application.errors import FlowNotEditableError, InvalidGraphError
from app.modules.workflow.domain.models import WorkflowFlow
from app.modules.workflow.domain.validation import validate_graph
from app.shared.audit import AuditContext, write_audit
from app.shared.exceptions import ResourceNotFoundError
from app.shared.permissions import Principal, permission_checker


def _audit_ctx(principal: Principal, ctx: RequestContext) -> AuditContext:
    return AuditContext(
        actor_id=principal.user_id,
        actor_org_id=principal.org_id,
        ip=ctx.ip,
        user_agent=ctx.user_agent,
    )


async def create_draft_flow(
    session: AsyncSession,
    *,
    principal: Principal,
    name: str,
    description: str | None,
    trigger_type: str,
    graph: dict,
    ctx: RequestContext,
) -> WorkflowFlow:
    permission_checker.require(principal, "workflow", "create", resource_org_id=principal.org_id)

    errors = validate_graph(graph)
    if errors:
        raise InvalidGraphError(errors)

    flow = WorkflowFlow(
        name=name,
        description=description,
        trigger_type=trigger_type,
        graph=graph,
        status="DRAFT",
        version=1,
        created_by=principal.user_id,
        created_at=datetime.now(tz=UTC),
    )
    session.add(flow)
    await session.flush()

    await write_audit(
        session,
        action="workflow.flow_created",
        resource_type="workflow_flow",
        resource_id=flow.id,
        context=_audit_ctx(principal, ctx),
        after={"name": name, "trigger_type": trigger_type, "status": "DRAFT"},
    )
    await session.commit()
    return flow


async def update_draft_flow(
    session: AsyncSession,
    *,
    principal: Principal,
    flow_id: uuid.UUID,
    name: str | None = None,
    description: str | None = None,
    graph: dict | None = None,
    ctx: RequestContext,
) -> WorkflowFlow:
    permission_checker.require(principal, "workflow", "update", resource_org_id=principal.org_id)
    flow = await get_flow(session, principal=principal, flow_id=flow_id)

    if flow.status != "DRAFT":
        raise FlowNotEditableError()

    before = {"name": flow.name, "graph": flow.graph}
    if graph is not None:
        errors = validate_graph(graph)
        if errors:
            raise InvalidGraphError(errors)
        flow.graph = graph
    if name is not None:
        flow.name = name
    if description is not None:
        flow.description = description

    await session.flush()
    await write_audit(
        session,
        action="workflow.flow_updated",
        resource_type="workflow_flow",
        resource_id=flow.id,
        context=_audit_ctx(principal, ctx),
        before=before,
        after={"name": flow.name, "graph": flow.graph},
    )
    await session.commit()
    return flow


async def get_flow(
    session: AsyncSession, *, principal: Principal, flow_id: uuid.UUID
) -> WorkflowFlow:
    permission_checker.require(principal, "workflow", "read", resource_org_id=principal.org_id)
    flow = await session.get(WorkflowFlow, flow_id)
    if flow is None:
        raise ResourceNotFoundError()
    return flow


async def list_flows(
    session: AsyncSession, *, principal: Principal, status: str | None = None
) -> list[WorkflowFlow]:
    permission_checker.require(principal, "workflow", "read", resource_org_id=principal.org_id)
    stmt = select(WorkflowFlow).order_by(WorkflowFlow.created_at.desc())
    if status is not None:
        stmt = stmt.where(WorkflowFlow.status == status)
    result = await session.execute(stmt)
    return list(result.scalars().all())
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && DEBUG=false uv run pytest tests/integration/test_workflow_flow_service.py -v`
Expected: 3 passed

If `add_member`'s actual signature/return differs from the test's assumption, fix the test to match the real helper (do not change `add_member` itself) and re-run.

- [ ] **Step 6: Commit**

```bash
cd backend && git add app/modules/workflow/application/ tests/workflow_utils.py tests/integration/test_workflow_flow_service.py
git commit -m "feat(workflow): add draft flow CRUD service with RBAC, graph validation, and audit"
```

---

### Task 5: Flow activation service (`workflow:activate`) — version immutability

**Files:**
- Create: `backend/app/modules/workflow/application/activation_service.py`
- Test: `backend/tests/integration/test_workflow_activation_service.py`

**Interfaces:**
- Consumes: `flow_service.get_flow` (Task 4).
- Produces: `activate_flow(session, *, principal, flow_id, ctx) -> WorkflowFlow`, `deactivate_flow(session, *, principal, flow_id, ctx) -> WorkflowFlow`, `create_new_draft_version(session, *, principal, flow_id, graph, ctx) -> WorkflowFlow` (editing an ACTIVE flow creates a new flow row versioned from the original, per `.claude/rules/realtime.md`: "cannot edit an active running version in place").

- [ ] **Step 1: Write failing tests**

```python
# backend/tests/integration/test_workflow_activation_service.py
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
        db_session, principal=admin, name="Partner approval", description=None,
        trigger_type="system.partner_registered", graph=VALID_GRAPH, ctx=CTX,
    )

    activated = await activation_service.activate_flow(db_session, principal=admin, flow_id=flow.id, ctx=CTX)

    assert activated.status == "ACTIVE"
    assert activated.activated_at is not None


@pytest.mark.asyncio
async def test_cannot_update_active_flow_in_place(db_session) -> None:
    _user, org, admin = await make_org_with_admin(db_session, org_type="university")
    flow = await flow_service.create_draft_flow(
        db_session, principal=admin, name="Partner approval", description=None,
        trigger_type="system.partner_registered", graph=VALID_GRAPH, ctx=CTX,
    )
    await activation_service.activate_flow(db_session, principal=admin, flow_id=flow.id, ctx=CTX)

    with pytest.raises(FlowNotEditableError):
        await flow_service.update_draft_flow(
            db_session, principal=admin, flow_id=flow.id, graph=VALID_GRAPH, ctx=CTX,
        )


@pytest.mark.asyncio
async def test_new_draft_version_created_from_active_flow(db_session) -> None:
    _user, org, admin = await make_org_with_admin(db_session, org_type="university")
    flow = await flow_service.create_draft_flow(
        db_session, principal=admin, name="Partner approval", description=None,
        trigger_type="system.partner_registered", graph=VALID_GRAPH, ctx=CTX,
    )
    await activation_service.activate_flow(db_session, principal=admin, flow_id=flow.id, ctx=CTX)

    new_draft = await activation_service.create_new_draft_version(
        db_session, principal=admin, flow_id=flow.id, graph=VALID_GRAPH, ctx=CTX,
    )

    assert new_draft.id != flow.id
    assert new_draft.status == "DRAFT"
    assert new_draft.version == flow.version + 1
```

- [ ] **Step 2: Run to verify failure**

Run: `cd backend && DEBUG=false uv run pytest tests/integration/test_workflow_activation_service.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.modules.workflow.application.activation_service'`

- [ ] **Step 3: Implement**

```python
# backend/app/modules/workflow/application/activation_service.py
from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.application.context import RequestContext
from app.modules.workflow.application import flow_service
from app.modules.workflow.domain.models import WorkflowFlow
from app.shared.audit import write_audit
from app.shared.permissions import Principal, permission_checker


async def activate_flow(
    session: AsyncSession, *, principal: Principal, flow_id: uuid.UUID, ctx: RequestContext
) -> WorkflowFlow:
    permission_checker.require(principal, "workflow", "activate", resource_org_id=principal.org_id)
    flow = await flow_service.get_flow(session, principal=principal, flow_id=flow_id)

    flow.status = "ACTIVE"
    flow.activated_at = datetime.now(tz=UTC)
    await session.flush()

    await write_audit(
        session,
        action="workflow.flow_activated",
        resource_type="workflow_flow",
        resource_id=flow.id,
        context=flow_service._audit_ctx(principal, ctx),
        after={"status": "ACTIVE", "trigger_type": flow.trigger_type},
    )
    await session.commit()
    return flow


async def deactivate_flow(
    session: AsyncSession, *, principal: Principal, flow_id: uuid.UUID, ctx: RequestContext
) -> WorkflowFlow:
    permission_checker.require(principal, "workflow", "activate", resource_org_id=principal.org_id)
    flow = await flow_service.get_flow(session, principal=principal, flow_id=flow_id)

    flow.status = "ARCHIVED"
    await session.flush()
    await write_audit(
        session,
        action="workflow.flow_deactivated",
        resource_type="workflow_flow",
        resource_id=flow.id,
        context=flow_service._audit_ctx(principal, ctx),
        after={"status": "ARCHIVED"},
    )
    await session.commit()
    return flow


async def create_new_draft_version(
    session: AsyncSession,
    *,
    principal: Principal,
    flow_id: uuid.UUID,
    graph: dict,
    ctx: RequestContext,
) -> WorkflowFlow:
    """An ACTIVE flow can never be edited in place. This creates a brand-new
    flow row carrying the next version number, left in DRAFT until separately
    activated (which then archives the prior ACTIVE version — left to the
    caller/UI flow, not auto-archived here, since a review step is expected
    per docs/BACKLOG.md B-394 dry-run gate before promotion).
    """

    original = await flow_service.get_flow(session, principal=principal, flow_id=flow_id)
    return await flow_service.create_draft_flow(
        session,
        principal=principal,
        name=original.name,
        description=original.description,
        trigger_type=original.trigger_type,
        graph=graph,
        ctx=ctx,
    )
```

Note: `create_new_draft_version` reuses `create_draft_flow`, so the new row's `version` is 1 in the DB column today — the test asserts `new_draft.version == flow.version + 1`, which will fail against this first-pass implementation. Fix by making `create_draft_flow` accept an optional `version: int = 1` and `source_flow_id` pass-through, or (simpler, do this) add a `version` param to `create_draft_flow`'s signature defaulting to `1`, and have `create_new_draft_version` pass `version=original.version + 1`. Update `create_draft_flow` and this call together before running Step 4.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && DEBUG=false uv run pytest tests/integration/test_workflow_activation_service.py tests/integration/test_workflow_flow_service.py -v`
Expected: all passed

- [ ] **Step 5: Commit**

```bash
cd backend && git add app/modules/workflow/application/activation_service.py app/modules/workflow/application/flow_service.py tests/integration/test_workflow_activation_service.py
git commit -m "feat(workflow): add activate/deactivate and immutable-active-version draft-forking"
```

---

### Task 6: Execution engine (`execute_flow` interpreter)

**Files:**
- Create: `backend/app/modules/workflow/application/execution_service.py`
- Test: `backend/tests/integration/test_workflow_execution_service.py`

**Interfaces:**
- Consumes: `WorkflowExecution`/`WorkflowFlow` (Task 2), `FlowContext` (Task 2).
- Produces: `async def execute_flow(session: AsyncSession, *, execution_id: uuid.UUID) -> None` — walks the graph node by node, updates `node_logs`, sets terminal `status`. Also produces a registered no-op Celery task wrapper `run_execute_flow_task` for the deferred production path.

- [ ] **Step 1: Write failing tests covering Condition branching, Action auto-approve, and Human Review pending state**

```python
# backend/tests/integration/test_workflow_execution_service.py
from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from app.modules.workflow.application import execution_service
from app.modules.workflow.domain.models import WorkflowExecution, WorkflowFlow

CONDITION_GRAPH = {
    "nodes": [
        {"id": "n1", "type": "trigger", "data": {"trigger_type": "system.partner_registered"}},
        {"id": "n2", "type": "condition", "data": {"expression": "{{fraud_score}} > 0.70"}},
        {
            "id": "n3",
            "type": "human_review",
            "data": {
                "assignee_mode": "queue",
                "assignee_department_id": "22222222-2222-2222-2222-222222222222",
                "sla_hours": 24,
            },
        },
        {"id": "n4", "type": "action", "data": {"action": "auto_approve"}},
        {"id": "n5", "type": "end", "data": {}},
    ],
    "edges": [
        {"source": "n1", "target": "n2"},
        {"source": "n2", "target": "n3", "condition": "true"},
        {"source": "n2", "target": "n4", "condition": "false"},
        {"source": "n3", "target": "n5"},
        {"source": "n4", "target": "n5"},
    ],
}


async def _make_flow_and_execution(db_session, *, trigger_event: dict) -> WorkflowExecution:
    flow = WorkflowFlow(
        id=uuid.uuid4(), name="Partner approval", description=None,
        trigger_type="system.partner_registered", graph=CONDITION_GRAPH,
        status="ACTIVE", version=1, created_by=uuid.uuid4(),
        created_at=datetime.now(tz=UTC),
    )
    db_session.add(flow)
    await db_session.flush()
    execution = WorkflowExecution(
        id=uuid.uuid4(), flow_id=flow.id, trigger_event=trigger_event,
        idempotency_key="evt-1", status="RUNNING",
        started_at=datetime.now(tz=UTC), node_logs=[],
    )
    db_session.add(execution)
    await db_session.flush()
    await db_session.commit()
    return execution


@pytest.mark.asyncio
async def test_low_fraud_score_auto_approves(db_session) -> None:
    execution = await _make_flow_and_execution(db_session, trigger_event={"fraud_score": 0.10})

    await execution_service.execute_flow(db_session, execution_id=execution.id)

    refreshed = await db_session.get(WorkflowExecution, execution.id)
    assert refreshed.status == "COMPLETED"
    node_types = [log["node_id"] for log in refreshed.node_logs]
    assert node_types == ["n1", "n2", "n4", "n5"]


@pytest.mark.asyncio
async def test_high_fraud_score_routes_to_human_review_and_pauses(db_session) -> None:
    execution = await _make_flow_and_execution(db_session, trigger_event={"fraud_score": 0.95})

    await execution_service.execute_flow(db_session, execution_id=execution.id)

    refreshed = await db_session.get(WorkflowExecution, execution.id)
    assert refreshed.status == "RUNNING"
    last_log = refreshed.node_logs[-1]
    assert last_log["node_id"] == "n3"
    assert last_log["decision"] == "awaiting_human_review"


@pytest.mark.asyncio
async def test_execution_is_idempotent_per_flow_and_event(db_session) -> None:
    execution = await _make_flow_and_execution(db_session, trigger_event={"fraud_score": 0.10})

    await execution_service.execute_flow(db_session, execution_id=execution.id)
    await execution_service.execute_flow(db_session, execution_id=execution.id)

    refreshed = await db_session.get(WorkflowExecution, execution.id)
    completed_end_logs = [log for log in refreshed.node_logs if log["node_id"] == "n5"]
    assert len(completed_end_logs) == 1
```

- [ ] **Step 2: Run to verify failure**

Run: `cd backend && DEBUG=false uv run pytest tests/integration/test_workflow_execution_service.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.modules.workflow.application.execution_service'`

- [ ] **Step 3: Implement the interpreter**

```python
# backend/app/modules/workflow/application/execution_service.py
"""Graph interpreter: walks a WorkflowFlow's graph node-by-node for a given
WorkflowExecution. Callable directly (tests, local/inline worker) and also
wrapped as a Celery task in ``celery_tasks.py`` for the deferred production
path — see docs/LOCAL_DEV_STACK.md on the inline-vs-Celery worker split.

Human Review nodes pause execution (status stays RUNNING) until a separate
review-decision call resumes the flow — that resume entrypoint is out of
scope for this plan (Phase A ships the auto-approve/condition/end path
end-to-end; the human-decision resume API is a fast-follow, tracked in the
plan's follow-up list, not silently implied here).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.workflow.domain.graph import FlowContext
from app.modules.workflow.domain.models import WorkflowExecution, WorkflowFlow


async def execute_flow(session: AsyncSession, *, execution_id: uuid.UUID) -> None:
    execution = await session.get(WorkflowExecution, execution_id)
    if execution is None or execution.status != "RUNNING":
        return

    flow = await session.get(WorkflowFlow, execution.flow_id)
    if flow is None:
        return

    if execution.node_logs:
        # Already progressed (idempotent re-entry, e.g. duplicate trigger
        # delivery) — do not replay from the start.
        return

    graph = flow.graph
    nodes_by_id = {n["id"]: n for n in graph["nodes"]}
    context = FlowContext(trigger=execution.trigger_event, variables={})

    current = _find_trigger_node(nodes_by_id)
    logs = list(execution.node_logs)

    while current is not None:
        entered_at = datetime.now(tz=UTC).isoformat()
        result = _execute_node(current, context)
        logs.append(
            {
                "node_id": current["id"],
                "entered_at": entered_at,
                "exited_at": datetime.now(tz=UTC).isoformat(),
                "decision": result.decision,
                "error": None,
            }
        )
        context.merge(result.output_variables)

        if result.decision == "awaiting_human_review":
            execution.node_logs = logs
            await session.commit()
            return
        if current["type"] == "end":
            execution.status = "COMPLETED"
            execution.finished_at = datetime.now(tz=UTC)
            execution.node_logs = logs
            await session.commit()
            return

        current = _resolve_next_node(nodes_by_id, graph["edges"], current, result.decision)

    execution.node_logs = logs
    execution.status = "COMPLETED"
    execution.finished_at = datetime.now(tz=UTC)
    await session.commit()


class _NodeResult:
    def __init__(self, decision: str, output_variables: dict | None = None) -> None:
        self.decision = decision
        self.output_variables = output_variables or {}


def _find_trigger_node(nodes_by_id: dict[str, dict]) -> dict | None:
    return next((n for n in nodes_by_id.values() if n["type"] == "trigger"), None)


def _execute_node(node: dict, context: FlowContext) -> _NodeResult:
    node_type = node["type"]
    data = node.get("data", {})

    if node_type == "trigger":
        return _NodeResult(decision="entered")
    if node_type == "condition":
        expression = context.interpolate(data["expression"])
        return _NodeResult(decision=str(eval(expression, {"__builtins__": {}})).lower())  # noqa: S307
    if node_type == "human_review":
        return _NodeResult(decision="awaiting_human_review")
    if node_type == "action":
        return _NodeResult(decision="done", output_variables={"action_taken": data.get("action")})
    if node_type == "delay":
        return _NodeResult(decision="done")
    if node_type == "end":
        return _NodeResult(decision="done")
    raise ValueError(f"unsupported node type: {node_type}")


def _resolve_next_node(
    nodes_by_id: dict[str, dict], edges: list[dict], current: dict, decision: str
) -> dict | None:
    candidates = [e for e in edges if e["source"] == current["id"]]
    if len(candidates) == 1 and "condition" not in candidates[0]:
        return nodes_by_id.get(candidates[0]["target"])
    for edge in candidates:
        if edge.get("condition") == decision:
            return nodes_by_id.get(edge["target"])
    return None
```

The `eval(...)` use above is a **known, deliberately narrow placeholder** for condition evaluation: it runs with `{"__builtins__": {}}` (no builtin access) against a string that has already been through `FlowContext.interpolate`, so no attacker-controlled Python syntax reaches it in this plan's two seed templates (Task 9 only uses `{{fraud_score}} > 0.70`-shaped expressions with numeric literals). This is a real security-hardening gap flagged for a follow-up task (a proper restricted expression grammar), not something to silently ship as final — record it in the handoff, do not remove this comment when implementing.

- [ ] **Step 4: Register the Celery task wrapper**

```python
# backend/app/modules/workflow/application/celery_tasks.py
"""Celery task registration for the deferred production execution path.
Not exercised by this plan's tests — those call ``execute_flow`` directly
per the inline-worker convention (docs/LOCAL_DEV_STACK.md).
"""

from __future__ import annotations

import asyncio
import uuid

from app.core.db import get_sessionmaker
from app.modules.automation.workers.celery_app import celery_app
from app.modules.workflow.application.execution_service import execute_flow


@celery_app.task(name="workflow.execute_flow", bind=True, max_retries=3)
def run_execute_flow_task(self, execution_id: str) -> None:
    async def _run() -> None:
        sessionmaker = get_sessionmaker()
        async with sessionmaker() as session:
            await execute_flow(session, execution_id=uuid.UUID(execution_id))

    asyncio.run(_run())
```

Run: `grep -n "def get_sessionmaker\|^async_session\|sessionmaker" backend/app/core/db.py` — if there is no `get_sessionmaker()` function, use whatever the file actually exposes (e.g. a module-level `async_session_factory`) and adjust the import/usage above to match exactly before committing.

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && DEBUG=false uv run pytest tests/integration/test_workflow_execution_service.py -v`
Expected: 3 passed

- [ ] **Step 6: Commit**

```bash
cd backend && git add app/modules/workflow/application/execution_service.py app/modules/workflow/application/celery_tasks.py tests/integration/test_workflow_execution_service.py
git commit -m "feat(workflow): add graph interpreter with condition branching, human review pause, and Celery task wrapper"
```

---

### Task 7: Trigger dispatch — idempotent enqueue + wiring into `verify_email` and `register_partner`

**Files:**
- Create: `backend/app/modules/workflow/application/trigger_service.py`
- Modify: `backend/app/modules/auth/application/auth_service.py` (inside `verify_email`, before `return user`)
- Modify: `backend/app/modules/organization/application/partner_registration_service.py` (inside `register_partner`, before `return {...}`)
- Test: `backend/tests/integration/test_workflow_trigger_service.py`

**Interfaces:**
- Consumes: `WorkflowFlow`/`WorkflowExecution` (Task 2), `execute_flow` (Task 6).
- Produces: `async def dispatch_trigger(session: AsyncSession, *, trigger_type: str, payload: dict, idempotency_key: str) -> list[uuid.UUID]` (returns created/reused execution IDs; runs `execute_flow` inline for each — Celery dispatch happens only from `celery_tasks.py`'s production wrapper, not from this function, so tests never need Celery).

- [ ] **Step 1: Write failing tests**

```python
# backend/tests/integration/test_workflow_trigger_service.py
from __future__ import annotations

import uuid

import pytest

from app.modules.workflow.application import activation_service, flow_service, trigger_service
from app.modules.workflow.domain.models import WorkflowExecution
from tests.auth_utils import CTX
from tests.org_utils import make_org_with_admin
from tests.workflow_utils import VALID_GRAPH


@pytest.mark.asyncio
async def test_dispatch_creates_execution_for_matching_active_flow(db_session) -> None:
    _user, org, admin = await make_org_with_admin(db_session, org_type="university")
    flow = await flow_service.create_draft_flow(
        db_session, principal=admin, name="Student verification", description=None,
        trigger_type="system.student_registered", graph=VALID_GRAPH, ctx=CTX,
    )
    await activation_service.activate_flow(db_session, principal=admin, flow_id=flow.id, ctx=CTX)

    execution_ids = await trigger_service.dispatch_trigger(
        db_session, trigger_type="system.student_registered",
        payload={"user_id": str(uuid.uuid4())}, idempotency_key="student-registered-u1",
    )

    assert len(execution_ids) == 1
    execution = await db_session.get(WorkflowExecution, execution_ids[0])
    assert execution.flow_id == flow.id


@pytest.mark.asyncio
async def test_dispatch_ignores_draft_and_archived_flows(db_session) -> None:
    _user, org, admin = await make_org_with_admin(db_session, org_type="university")
    await flow_service.create_draft_flow(
        db_session, principal=admin, name="Draft only", description=None,
        trigger_type="system.student_registered", graph=VALID_GRAPH, ctx=CTX,
    )

    execution_ids = await trigger_service.dispatch_trigger(
        db_session, trigger_type="system.student_registered",
        payload={"user_id": str(uuid.uuid4())}, idempotency_key="student-registered-u2",
    )

    assert execution_ids == []


@pytest.mark.asyncio
async def test_dispatch_is_idempotent_for_same_key(db_session) -> None:
    _user, org, admin = await make_org_with_admin(db_session, org_type="university")
    flow = await flow_service.create_draft_flow(
        db_session, principal=admin, name="Student verification", description=None,
        trigger_type="system.student_registered", graph=VALID_GRAPH, ctx=CTX,
    )
    await activation_service.activate_flow(db_session, principal=admin, flow_id=flow.id, ctx=CTX)

    first = await trigger_service.dispatch_trigger(
        db_session, trigger_type="system.student_registered",
        payload={"user_id": "u1"}, idempotency_key="dup-key",
    )
    second = await trigger_service.dispatch_trigger(
        db_session, trigger_type="system.student_registered",
        payload={"user_id": "u1"}, idempotency_key="dup-key",
    )

    assert first == second
```

- [ ] **Step 2: Run to verify failure**

Run: `cd backend && DEBUG=false uv run pytest tests/integration/test_workflow_trigger_service.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement `dispatch_trigger`**

```python
# backend/app/modules/workflow/application/trigger_service.py
"""Public entrypoint other modules call to notify the workflow engine that a
business event happened. This is the one function other modules are allowed
to import directly (mirrors how ``enqueue_notification`` is imported across
module boundaries elsewhere in this codebase) — no other workflow internals
should be reached into from outside this module.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.workflow.application.execution_service import execute_flow
from app.modules.workflow.domain.models import WorkflowExecution, WorkflowFlow


async def dispatch_trigger(
    session: AsyncSession,
    *,
    trigger_type: str,
    payload: dict,
    idempotency_key: str,
) -> list[uuid.UUID]:
    active_flows = (
        await session.execute(
            select(WorkflowFlow).where(
                WorkflowFlow.trigger_type == trigger_type,
                WorkflowFlow.status == "ACTIVE",
            )
        )
    ).scalars().all()

    execution_ids: list[uuid.UUID] = []
    for flow in active_flows:
        existing = (
            await session.execute(
                select(WorkflowExecution).where(
                    WorkflowExecution.flow_id == flow.id,
                    WorkflowExecution.idempotency_key == idempotency_key,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            execution_ids.append(existing.id)
            continue

        execution = WorkflowExecution(
            id=uuid.uuid4(),
            flow_id=flow.id,
            trigger_event=payload,
            idempotency_key=idempotency_key,
            status="RUNNING",
            started_at=datetime.now(tz=UTC),
            node_logs=[],
        )
        session.add(execution)
        await session.flush()
        execution_ids.append(execution.id)

    await session.commit()

    for execution_id in execution_ids:
        await execute_flow(session, execution_id=execution_id)

    return execution_ids
```

- [ ] **Step 4: Run trigger-service tests to verify they pass, before wiring real call sites**

Run: `cd backend && DEBUG=false uv run pytest tests/integration/test_workflow_trigger_service.py -v`
Expected: 3 passed

- [ ] **Step 5: Wire `dispatch_trigger` into `auth_service.verify_email`**

In `backend/app/modules/auth/application/auth_service.py`, find `verify_email` (search `async def verify_email`). Add the import at the top of the file next to the existing `write_audit`/`record_security_event` imports:

```python
from app.modules.workflow.application.trigger_service import dispatch_trigger
```

Inside `verify_email`, immediately after the existing `await write_audit(...)` call and before `await session.commit()`, add:

```python
    await dispatch_trigger(
        session,
        trigger_type="system.student_registered",
        payload={"user_id": str(user.id), "email": user.email},
        idempotency_key=f"student_registered:{user.id}",
    )
```

- [ ] **Step 6: Wire `dispatch_trigger` into `partner_registration_service.register_partner`**

In `backend/app/modules/organization/application/partner_registration_service.py`, add the same import, then inside `register_partner`, immediately after the existing `await enqueue_notification(...)` call and before `await session.commit()`, add:

```python
    await dispatch_trigger(
        session,
        trigger_type="system.partner_registered",
        payload={"registration_id": str(req.id), "company_name": req.company_name},
        idempotency_key=f"partner_registered:{req.id}",
    )
```

- [ ] **Step 7: Write an end-to-end test proving the real call sites fire**

```python
# backend/tests/integration/test_workflow_trigger_wiring.py
from __future__ import annotations

import pytest

from app.modules.auth.application import auth_service
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
        db_session, principal=admin, name="Student verification", description=None,
        trigger_type="system.student_registered", graph=VALID_GRAPH, ctx=CTX,
    )
    await activation_service.activate_flow(db_session, principal=admin, flow_id=flow.id, ctx=CTX)

    await auth_service.register(
        db_session, email="new.student@example.com", password="Str0ngPassw0rd!",
        full_name="New Student", ctx=CTX,
    )
    token = await fetch_verification_token(db_session, user_id=None)  # see Step 8 note
    await auth_service.verify_email(db_session, token=token, ctx=CTX)

    executions = (await db_session.execute(select(WorkflowExecution))).scalars().all()
    assert any(e.flow_id == flow.id for e in executions)
```

- [ ] **Step 8: Reconcile the test helper signature**

Run: `grep -n "async def fetch_verification_token" -A 10 backend/tests/auth_utils.py` to see its real parameters (it may require a `user_id`, not `None`, or may look up by email instead). Adjust the test in Step 7 to call it correctly — do not guess; use exactly what that function requires.

- [ ] **Step 9: Run the full workflow test suite**

Run: `cd backend && DEBUG=false uv run pytest tests/integration/test_workflow_trigger_service.py tests/integration/test_workflow_trigger_wiring.py -v`
Expected: all passed

- [ ] **Step 10: Commit**

```bash
cd backend && git add app/modules/workflow/application/trigger_service.py app/modules/auth/application/auth_service.py app/modules/organization/application/partner_registration_service.py tests/integration/test_workflow_trigger_service.py tests/integration/test_workflow_trigger_wiring.py
git commit -m "feat(workflow): add idempotent trigger dispatch wired into email verification and partner registration"
```

---

### Task 8: API router + schemas + mount

**Files:**
- Create: `backend/app/modules/workflow/api/__init__.py`
- Create: `backend/app/modules/workflow/api/schemas.py`
- Create: `backend/app/modules/workflow/api/router.py`
- Modify: `backend/app/bootstrap/routes.py`
- Test: `backend/tests/integration/test_workflow_api.py`

**Interfaces:**
- Consumes: `flow_service`, `activation_service` (Tasks 4/5), `app.shared.responses.success`, `app.core.db.get_db_session`, `app.modules.auth.api.deps.CurrentAuth`/`get_current_auth`.
- Produces: `POST /api/v1/workflows`, `PATCH /api/v1/workflows/{flow_id}`, `GET /api/v1/workflows/{flow_id}`, `GET /api/v1/workflows`, `POST /api/v1/workflows/{flow_id}/activate`, `POST /api/v1/workflows/{flow_id}/deactivate` — per `docs/API_CONTRACTS.md`'s existing `/workflows` table.

- [ ] **Step 1: Write failing API tests**

```python
# backend/tests/integration/test_workflow_api.py
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from tests.org_utils import make_org_with_admin


@pytest.mark.asyncio
async def test_create_and_activate_flow_via_api(db_session, access_token_for) -> None:
    _user, org, admin = await make_org_with_admin(db_session, org_type="university")
    token = await access_token_for(admin)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        create_resp = await client.post(
            "/api/v1/workflows",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "name": "Student verification",
                "description": None,
                "trigger_type": "system.student_registered",
                "graph": {
                    "nodes": [
                        {"id": "n1", "type": "trigger", "data": {"trigger_type": "system.student_registered"}},
                        {"id": "n2", "type": "end", "data": {}},
                    ],
                    "edges": [{"source": "n1", "target": "n2"}],
                },
            },
        )
        assert create_resp.status_code == 200
        flow_id = create_resp.json()["data"]["id"]

        activate_resp = await client.post(
            f"/api/v1/workflows/{flow_id}/activate",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert activate_resp.status_code == 200
        assert activate_resp.json()["data"]["status"] == "ACTIVE"
```

Run: `grep -rn "access_token_for\|def.*access_token" backend/tests/conftest.py backend/tests/auth_utils.py` — if no such fixture/helper exists yet, use whatever the existing API-level tests in this repo actually do to authenticate a request (e.g. `grep -rln "Authorization.*Bearer" backend/tests/integration/*.py | head -3` and copy that exact pattern) instead of inventing `access_token_for`.

- [ ] **Step 2: Run to verify failure**

Run: `cd backend && DEBUG=false uv run pytest tests/integration/test_workflow_api.py -v`
Expected: FAIL (404, since no router mounted yet)

- [ ] **Step 3: Implement schemas and router**

```python
# backend/app/modules/workflow/api/__init__.py
```

```python
# backend/app/modules/workflow/api/schemas.py
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
```

```python
# backend/app/modules/workflow/api/router.py
"""Workflow flow HTTP routes: HTTP-only, delegates RBAC/audit to application
services, per docs/API_CONTRACTS.md's /workflows contract.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query

from app.core.db import get_db_session
from app.modules.auth.api.deps import CurrentAuth, get_current_auth
from app.modules.workflow.api.schemas import CreateFlowRequest, UpdateFlowRequest
from app.modules.workflow.application import activation_service, flow_service
from app.shared.responses import success
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends as _Depends  # noqa: F401  (keeps import grouping consistent)

router = APIRouter(prefix="/workflows", tags=["workflow"])


def _presenter(flow) -> dict:
    return {
        "id": str(flow.id),
        "name": flow.name,
        "description": flow.description,
        "trigger_type": flow.trigger_type,
        "status": flow.status,
        "version": flow.version,
        "graph": flow.graph,
    }


@router.post("")
async def create_flow(
    body: CreateFlowRequest,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    flow = await flow_service.create_draft_flow(
        session, principal=auth.principal, name=body.name, description=body.description,
        trigger_type=body.trigger_type, graph=body.graph, ctx=auth.ctx,
    )
    return success(_presenter(flow))


@router.patch("/{flow_id}")
async def update_flow(
    flow_id: uuid.UUID,
    body: UpdateFlowRequest,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    flow = await flow_service.update_draft_flow(
        session, principal=auth.principal, flow_id=flow_id, name=body.name,
        description=body.description, graph=body.graph, ctx=auth.ctx,
    )
    return success(_presenter(flow))


@router.get("/{flow_id}")
async def get_flow(
    flow_id: uuid.UUID,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    flow = await flow_service.get_flow(session, principal=auth.principal, flow_id=flow_id)
    return success(_presenter(flow))


@router.get("")
async def list_flows(
    status_filter: str | None = Query(default=None, alias="status"),
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    flows = await flow_service.list_flows(session, principal=auth.principal, status=status_filter)
    return success([_presenter(f) for f in flows])


@router.post("/{flow_id}/activate")
async def activate_flow(
    flow_id: uuid.UUID,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    flow = await activation_service.activate_flow(session, principal=auth.principal, flow_id=flow_id, ctx=auth.ctx)
    return success(_presenter(flow))


@router.post("/{flow_id}/deactivate")
async def deactivate_flow(
    flow_id: uuid.UUID,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    flow = await activation_service.deactivate_flow(session, principal=auth.principal, flow_id=flow_id, ctx=auth.ctx)
    return success(_presenter(flow))
```

- [ ] **Step 4: Mount the router**

In `backend/app/bootstrap/routes.py`, add the import alongside the other module router imports:

```python
from app.modules.workflow.api import router as workflow_router
```

And add the mount call alongside the others inside `register_routes`:

```python
    api.include_router(workflow_router.router)
```

- [ ] **Step 5: Run the API test**

Run: `cd backend && DEBUG=false uv run pytest tests/integration/test_workflow_api.py -v`
Expected: 1 passed. If the auth-header helper from Step 1 doesn't exist, fix the test to use the repo's real login/token-issuance helper before this passes — do not stub around authentication.

- [ ] **Step 6: Run full backend suite to check for regressions**

Run: `cd backend && DEBUG=false uv run pytest -q`
Expected: all tests pass (no regressions in unrelated modules from the `auth_service`/`partner_registration_service` edits in Task 7).

- [ ] **Step 7: Commit**

```bash
cd backend && git add app/modules/workflow/api/ app/bootstrap/routes.py tests/integration/test_workflow_api.py
git commit -m "feat(workflow): add flow CRUD/activate/deactivate API and mount under /api/v1/workflows"
```

---

### Task 9: Seed the two Phase-A templates (student verification, partner/employer approval)

**Files:**
- Create: `backend/scripts/seed_workflow_templates.py`
- Test: `backend/tests/integration/test_workflow_templates_seed.py`

**Interfaces:**
- Consumes: `flow_service.create_draft_flow`, `activation_service.activate_flow`.
- Produces: `async def seed_templates(session: AsyncSession, *, principal: Principal, ctx: RequestContext) -> list[WorkflowFlow]` — idempotent (skips a template if a flow with the same `name` already exists), used by the seed script and directly by the test.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/integration/test_workflow_templates_seed.py
from __future__ import annotations

import pytest

from scripts.seed_workflow_templates import seed_templates
from tests.auth_utils import CTX
from tests.org_utils import make_org_with_admin


@pytest.mark.asyncio
async def test_seed_creates_both_templates_active(db_session) -> None:
    _user, org, admin = await make_org_with_admin(db_session, org_type="university")

    flows = await seed_templates(db_session, principal=admin, ctx=CTX)

    assert {f.name for f in flows} == {"Student verification", "Partner/employer account approval"}
    assert all(f.status == "ACTIVE" for f in flows)


@pytest.mark.asyncio
async def test_seed_is_idempotent(db_session) -> None:
    _user, org, admin = await make_org_with_admin(db_session, org_type="university")

    first = await seed_templates(db_session, principal=admin, ctx=CTX)
    second = await seed_templates(db_session, principal=admin, ctx=CTX)

    assert {f.id for f in first} == {f.id for f in second}
```

- [ ] **Step 2: Run to verify failure**

Run: `cd backend && DEBUG=false uv run pytest tests/integration/test_workflow_templates_seed.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'scripts.seed_workflow_templates'`

- [ ] **Step 3: Implement the seed module**

```python
# backend/scripts/seed_workflow_templates.py
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

STUDENT_VERIFICATION_GRAPH = {
    "nodes": [
        {"id": "trigger", "type": "trigger", "data": {"trigger_type": "system.student_registered"}},
        {"id": "check_domain", "type": "condition", "data": {"expression": "{{is_university_email}} == True"}},
        {"id": "auto_approve", "type": "action", "data": {"action": "auto_approve"}},
        {
            "id": "manual_review",
            "type": "human_review",
            "data": {"assignee_mode": "queue", "assignee_department_id": None, "sla_hours": 48},
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

PARTNER_APPROVAL_GRAPH = {
    "nodes": [
        {"id": "trigger", "type": "trigger", "data": {"trigger_type": "system.partner_registered"}},
        {
            "id": "manual_review",
            "type": "human_review",
            "data": {"assignee_mode": "queue", "assignee_department_id": None, "sla_hours": 72},
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
    templates = [
        ("Student verification", "system.student_registered", STUDENT_VERIFICATION_GRAPH),
        (
            "Partner/employer account approval",
            "system.partner_registered",
            PARTNER_APPROVAL_GRAPH,
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
```

Note: the seed graphs use `assignee_department_id: None`, which will fail `validate_graph`'s Human Review check from Task 3 (`assignee_mode=queue requires assignee_department_id`). Before running Step 4, either (a) seed a real placeholder department/role via the `organization` module first and pass its id, or (b) relax the seed graphs to `assignee_mode: "person"` with a real `assignee_user_id` (e.g. the seeding principal's own `user_id`, since a university admin is a legitimate first-pass reviewer for seed/demo purposes). Prefer (b) for this plan — it needs zero new organization-module fixtures — and update both graphs' `manual_review`/`send_email` review node accordingly, replacing `"assignee_mode": "queue", "assignee_department_id": None` with `"assignee_mode": "person", "assignee_user_id": str(principal.user_id)` at seed-call time (build the graph dict inside `seed_templates` after `principal` is known, rather than as a module-level constant, since it now depends on the caller).

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && DEBUG=false uv run pytest tests/integration/test_workflow_templates_seed.py -v`
Expected: 2 passed

- [ ] **Step 5: Run the entire backend test suite one final time**

Run: `cd backend && DEBUG=false uv run pytest -q`
Expected: all passed, no regressions.

- [ ] **Step 6: Commit**

```bash
cd backend && git add backend/scripts/seed_workflow_templates.py tests/integration/test_workflow_templates_seed.py
git commit -m "feat(workflow): seed student-verification and partner-approval templates end to end"
```

---

## Explicitly out of scope for this plan (tracked as follow-ups, not silently dropped)

- **Human-review resume/decision API** (an admin claims a pending Human Review node and the flow continues) — Phase A proves the auto-approve/condition/end path end to end; the resume endpoint is a fast-follow before Phase B canvas work is meaningful for real approvals.
- **SLA breach escalation job** (docs/BUSINESS_LOGIC.md §16.1) — needs a scheduled sweep (add to `app/modules/automation/scheduler/jobs.py` `REGISTRY`) checking for `RUNNING` executions paused at a Human Review node past `sla_hours`; not built in this plan.
- **Max-100-concurrent/FIFO-10k queueing** (docs/BUSINESS_LOGIC.md §16.1) — this plan's `dispatch_trigger` executes inline and unbounded; the queue/concurrency cap needs the Celery path wired for real, which is deferred per `docs/LOCAL_DEV_STACK.md`'s inline-first default.
- **Restricted expression grammar for Condition nodes** — flagged inline in Task 6; the current `eval()` with empty builtins is a stopgap, not hardened for arbitrary admin-authored expressions.
- **Phase B (React Flow canvas)** and **AI Provider Routing Canvas** (`ai_settings`) are separate plans per the design doc (`docs/superpowers/specs/2026-07-02-no-code-workflow-and-ai-routing-canvas-design.md` §6) — write those after this plan ships and is verified.
- **Docs updates** listed in the design spec §5 (`docs/DATA_MODEL.md`, `docs/BACKLOG.md` re-sequencing, `docs/BUSINESS_LOGIC.md` §16 Human Review schema doc update, `docs/IMPLEMENTATION_STATUS.md` reprioritization note) are not part of this code plan — do them as a short doc-only follow-up once Phase A is verified working.

## Self-review notes (already applied above, kept here as a record)

- Confirmed `write_audit`'s `before`/`after` are optional (no NOT NULL concern) per the investigation report — used correctly throughout.
- Confirmed the permission catalog is a hardcoded dict requiring a code change (Task 1), not just a migration.
- Confirmed no `ai_task_model_configs` table exists in code (real tables are `ai_provider_configs`/`ai_model_aliases`) — irrelevant to this plan since Phase A doesn't touch `ai_settings`, but keep this in mind when writing the AI Routing Canvas plan next.
- Flagged two known placeholders that must NOT be treated as silently resolved: the `eval()`-based condition evaluator (Task 6) and the deferred Human Review resume API (listed above) — both require explicit follow-up tasks, not silent scope-narrowing.
- Task 4/7/8's tests assume helper functions (`add_member`, `fetch_verification_token`, an auth-header/login helper) whose exact signatures were not fully confirmed during planning — each such step includes an explicit `grep`/verification instruction rather than guessing, per this plan's own no-placeholder rule.
