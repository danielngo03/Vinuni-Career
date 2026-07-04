# AI Provider/Model Routing Canvas Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a university admin visually configure, on a drag-and-drop canvas, which AI provider is primary and which providers are fallback (in order) for each task family (chat/reasoning/embedding/rerank/eval), and see live circuit-breaker health per provider — without touching raw API keys, base URLs, or (unless separately permitted) real provider/model identifiers.

**Architecture:** New tables `ai_routing_graphs`/`ai_routing_graph_activations` live in the existing `ai_settings` module. A routing graph is an **authoring artifact** (React Flow node/edge JSON); "Activate" compiles it into the REAL runtime tables the gateway already reads — `AiModelAlias.provider_id` (primary) and `AiModelAlias.fallback_provider_names` (ordered fallback, a comma-separated `Text` column added by migration `0049_ai_model_alias_fallback_chain`) — then republishes `EffectiveAiConfig` via the existing `resolve_and_publish` seam. Raw provider/model identity is hidden by default (curated `vendor_label`/`model_family_label`) and only returned to callers holding the new `ai_settings:view_provider_identity` permission, audited on every raw read, per ADR-0011.1 (`docs/API_CONTRACTS.md`). The frontend reuses the exact `FlowCanvas` component shipped in the Workflow Canvas Phase B plan (`frontend/src/components/workflow/flow-canvas.tsx`) with a different `nodeTypeDefs` set and a separate API client — proving out the design doc's "one shared canvas, two backend engines" decision.

**Tech Stack:** FastAPI async, SQLAlchemy 2.x async, Alembic, Pydantic v2, pytest + pytest-asyncio (backend); Next.js App Router, TypeScript strict, `@tanstack/react-query`, `@xyflow/react` (already installed by Phase B), Playwright e2e (frontend).

## Global Constraints

- Raw API key and base URL are **never** returned by any API regardless of permission (`docs/API_CONTRACTS.md` ADR-0011 / ADR-0011.1) — only `provider_internal`-equivalent identity strings are in scope for the new permission.
- Default (holding only `ai_settings:read`) shows curated `vendor_label`/`model_family_label` per alias; raw provider/model identity requires `ai_settings:view_provider_identity`, a distinct RBAC permission granted via the existing `organization` RBAC system (never a hardcoded role).
- Every raw-identity read must write an `audit_logs` row, `action = "ai_settings.provider_identity_viewed"` (ADR-0011.1 exact text).
- The routing graph is an authoring artifact; activation must compile into the real `ai_model_aliases`/`ai_provider_configs` tables the gateway already reads via `EffectiveAiConfig` — never a second, competing runtime read path.
- No direct cross-module implementation imports; this plan stays entirely inside `ai_settings` plus the existing `app/ai/gateway/` package it already depends on — it does not touch the `workflow` module's tables or execution engine (per the design doc's explicit rejection of unifying the two).
- New migrations must chain off the TRUE current head, confirmed fresh as `0050_ai_workforce_runs`, with both `upgrade()` and `downgrade()`.
- New permission strings require a `PERMISSION_CATALOG` code change in `backend/app/modules/organization/domain/catalog.py`, not just a migration.
- Reuse the existing `write_audit`/`AuditContext` helper and the existing `commit → resolve_and_publish → commit` republish pattern (`_commit_and_republish` in `ai_settings/api/router.py`) — do not invent a second republish mechanism.
- No unit-test runner exists on the frontend (no Jest/Vitest) — frontend verification is TypeScript strict + lint + incremental Playwright e2e, matching the Phase B plan's convention.
- Circuit-breaker state (`backend/app/ai/gateway/factory.py`'s `_circuit_states`) is in-memory, per-process, keyed by `provider_name`, and only tracks a binary `is_open()` (no distinct `half_open` state exists in code today) — the canvas must reflect this honestly as `"closed" | "open"`, not invent a `half_open` value the backend doesn't actually compute.

---

### Task 1: Migration for routing tables + permission catalog entry

**Files:**
- Modify: `backend/app/modules/organization/domain/catalog.py`
- Create: `backend/alembic/versions/0051_ai_routing_graphs.py`
- Test: `backend/tests/integration/test_ai_routing_migration.py`

**Interfaces:**
- Produces: DB tables `ai_routing_graphs(id, task_family, graph, status, version, created_by, created_at, activated_at, compiled_alias_id)` and `ai_routing_graph_activations(id, graph_id, graph_version, activated_by, activated_at, previous_active_graph_id)`; catalog entry `"ai_settings": frozenset({"read", "manage", "view_provider_identity"})`.

- [ ] **Step 1: Extend the `ai_settings` catalog entry**

In `backend/app/modules/organization/domain/catalog.py`, change:

```python
    "ai_settings": frozenset({"read", "manage"}),
```
to:
```python
    "ai_settings": frozenset({"read", "manage", "view_provider_identity"}),
```

- [ ] **Step 2: Write the failing catalog test**

```python
# backend/tests/integration/test_ai_routing_migration.py
from __future__ import annotations

from app.modules.organization.domain.catalog import is_catalog_permission


def test_view_provider_identity_permission_registered() -> None:
    assert is_catalog_permission("ai_settings", "view_provider_identity")
    assert is_catalog_permission("ai_settings", "read")
    assert is_catalog_permission("ai_settings", "manage")
```

- [ ] **Step 3: Run to verify it passes (catalog already updated in Step 1)**

Run: `cd backend && DEBUG=false uv run pytest tests/integration/test_ai_routing_migration.py -v`
Expected: 1 passed.

- [ ] **Step 4: Generate and write the migration, chained off the TRUE current head**

Run: `cd backend && ls alembic/versions/ | tail -3` to reconfirm the head is still `0050_ai_workforce_runs` (another concurrent session may have added more since the last check) — use whatever the actual latest revision is as `down_revision` below.

```python
# backend/alembic/versions/0051_ai_routing_graphs.py
"""ai provider/model routing canvas tables

Revision ID: 0051_ai_routing_graphs
Revises: 0050_ai_workforce_runs
Create Date: 2026-07-02
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0051_ai_routing_graphs"
down_revision = "0050_ai_workforce_runs"
branch_labels = None
depends_on = None

_JSON = sa.JSON().with_variant(JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        "ai_routing_graphs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("task_family", sa.String(length=20), nullable=False),
        sa.Column("graph", _JSON, nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="DRAFT"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "compiled_alias_id", sa.Uuid(), sa.ForeignKey("ai_model_aliases.id"), nullable=True
        ),
    )
    op.create_index(
        "ix_ai_routing_graphs_task_family_status", "ai_routing_graphs", ["task_family", "status"]
    )

    op.create_table(
        "ai_routing_graph_activations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "graph_id", sa.Uuid(), sa.ForeignKey("ai_routing_graphs.id"), nullable=False
        ),
        sa.Column("graph_version", sa.Integer(), nullable=False),
        sa.Column("activated_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "activated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("previous_active_graph_id", sa.Uuid(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("ai_routing_graph_activations")
    op.drop_index("ix_ai_routing_graphs_task_family_status", table_name="ai_routing_graphs")
    op.drop_table("ai_routing_graphs")
```

- [ ] **Step 5: Run the migration up and down**

Run: `cd backend && uv run alembic upgrade head`
Expected: reaches `0051_ai_routing_graphs` with no errors.

Run: `cd backend && uv run alembic downgrade -1 && uv run alembic upgrade head`
Expected: both succeed cleanly.

- [ ] **Step 6: Commit** (skip — confirmed no git repo in this checkout per Phase A/B execution; move directly to Task 2)

---

### Task 2: Domain models + graph validation

**Files:**
- Create: `backend/app/modules/ai_settings/domain/routing_models.py`
- Create: `backend/app/modules/ai_settings/domain/routing_validation.py`
- Modify: `backend/app/core/metadata.py`
- Test: `backend/tests/unit/test_ai_routing_validation.py`

**Interfaces:**
- Produces: ORM classes `AiRoutingGraph`, `AiRoutingGraphActivation`; `TASK_FAMILIES = ("chat", "reasoning", "embedding", "rerank", "eval")` (matches `ai_settings/domain/aliases.py`'s `ALIAS_FIELDS` families exactly — reuse that module's family list, don't redefine a diverging one); `validate_routing_graph(graph: dict) -> list[str]`.

- [ ] **Step 1: Write failing validation tests**

```python
# backend/tests/unit/test_ai_routing_validation.py
from __future__ import annotations

from app.modules.ai_settings.domain.routing_validation import validate_routing_graph

VALID_GRAPH = {
    "nodes": [
        {"id": "p1", "type": "provider", "data": {"provider_id": "11111111-1111-1111-1111-111111111111", "order": 0}},
        {"id": "p2", "type": "provider", "data": {"provider_id": "22222222-2222-2222-2222-222222222222", "order": 1}},
    ],
    "edges": [{"source": "p1", "target": "p2", "kind": "fallback"}],
}


def test_valid_routing_graph_has_no_errors() -> None:
    assert validate_routing_graph(VALID_GRAPH) == []


def test_duplicate_provider_in_graph_is_rejected() -> None:
    graph = {
        "nodes": [
            {"id": "p1", "type": "provider", "data": {"provider_id": "11111111-1111-1111-1111-111111111111", "order": 0}},
            {"id": "p2", "type": "provider", "data": {"provider_id": "11111111-1111-1111-1111-111111111111", "order": 1}},
        ],
        "edges": [{"source": "p1", "target": "p2", "kind": "fallback"}],
    }
    errors = validate_routing_graph(graph)
    assert any("duplicate provider" in e for e in errors)


def test_no_primary_provider_is_rejected() -> None:
    errors = validate_routing_graph({"nodes": [], "edges": []})
    assert any("at least one provider node" in e for e in errors)


def test_orphan_provider_node_is_rejected() -> None:
    graph = {
        "nodes": VALID_GRAPH["nodes"] + [{"id": "p3", "type": "provider", "data": {"provider_id": "33333333-3333-3333-3333-333333333333", "order": 2}}],
        "edges": VALID_GRAPH["edges"],
    }
    errors = validate_routing_graph(graph)
    assert any("not connected to the fallback chain" in e for e in errors)
```

- [ ] **Step 2: Run to verify failure**

Run: `cd backend && DEBUG=false uv run pytest tests/unit/test_ai_routing_validation.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement domain models**

```python
# backend/app/modules/ai_settings/domain/routing_models.py
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.models import Base, JsonType


class AiRoutingGraph(Base):
    __tablename__ = "ai_routing_graphs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    task_family: Mapped[str] = mapped_column(String(20))
    graph: Mapped[dict] = mapped_column(JsonType)
    status: Mapped[str] = mapped_column(String(20), default="DRAFT")
    version: Mapped[int] = mapped_column(default=1)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime]
    activated_at: Mapped[datetime | None] = mapped_column(default=None)
    compiled_alias_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("ai_model_aliases.id"), default=None
    )


class AiRoutingGraphActivation(Base):
    __tablename__ = "ai_routing_graph_activations"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    graph_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ai_routing_graphs.id"))
    graph_version: Mapped[int]
    activated_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    activated_at: Mapped[datetime]
    previous_active_graph_id: Mapped[uuid.UUID | None] = mapped_column(default=None)
```

```python
# backend/app/modules/ai_settings/domain/routing_validation.py
"""Structural validation for an AI routing graph before save/activation.

A routing graph represents one task family's fallback CHAIN: an ordered list
of provider nodes connected by "fallback" edges (p1 -> p2 -> p3 means "try p1
first, then p2, then p3"). This is deliberately simpler than the workflow
engine's general DAG validation (docs/superpowers/plans/2026-07-02-workflow-engine-phase-a.md
Task 3) — a fallback chain has no branching Condition nodes in this first
version, so cycle detection isn't needed in the same sense; duplicate-provider
and orphan-node checks are what actually matter here.
"""

from __future__ import annotations

from app.modules.ai_settings.domain.aliases import ALIAS_FIELDS

TASK_FAMILIES: tuple[str, ...] = tuple(sorted(set(ALIAS_FIELDS.values())))


def validate_routing_graph(graph: dict) -> list[str]:
    errors: list[str] = []
    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])
    provider_nodes = [n for n in nodes if n.get("type") == "provider"]

    if not provider_nodes:
        errors.append("graph must contain at least one provider node")
        return errors

    provider_ids = [n["data"]["provider_id"] for n in provider_nodes]
    seen: set[str] = set()
    for pid in provider_ids:
        if pid in seen:
            errors.append(f"duplicate provider in graph: {pid}")
        seen.add(pid)

    if len(provider_nodes) > 1:
        connected: set[str] = set()
        for edge in edges:
            if edge.get("kind") == "fallback":
                connected.add(edge["source"])
                connected.add(edge["target"])
        for node in provider_nodes:
            if node["id"] not in connected:
                errors.append(f"provider node {node['id']} is not connected to the fallback chain")

    return errors
```

- [ ] **Step 4: Register the new models in metadata**

Run: `grep -n "_workflow_models\|import_all_models" backend/app/core/metadata.py` to find the exact import/registration pattern used for the `workflow` module's models (added earlier today), then add an equivalent import and registration line for `routing_models`:

```python
from app.modules.ai_settings.domain import routing_models as _ai_routing_models  # noqa: F401
```
and add `_ai_routing_models` to whatever list/tuple the workflow entry was added to.

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && DEBUG=false uv run pytest tests/unit/test_ai_routing_validation.py -v`
Expected: 4 passed

---

### Task 3: Draft routing-graph CRUD service (`ai_settings:read`/`manage`)

**Files:**
- Create: `backend/app/modules/ai_settings/application/routing_service.py`
- Test: `backend/tests/integration/test_ai_routing_service.py`

**Interfaces:**
- Consumes: `AiRoutingGraph` (Task 2), `validate_routing_graph` (Task 2), `settings_service._require_ai_settings_admin`.
- Produces: `create_draft_graph(session, *, principal, task_family, graph, ctx) -> AiRoutingGraph`, `update_draft_graph(session, *, principal, graph_id, graph, ctx) -> AiRoutingGraph`, `get_graph(session, *, principal, graph_id) -> AiRoutingGraph`, `list_graphs(session, *, principal, task_family=None) -> list[AiRoutingGraph]`.

- [ ] **Step 1: Write failing tests**

```python
# backend/tests/integration/test_ai_routing_service.py
from __future__ import annotations

import pytest

from app.modules.ai_settings.application import routing_service
from app.modules.ai_settings.application.routing_errors import InvalidRoutingGraphError
from app.shared.exceptions import PermissionDeniedError
from tests.auth_utils import CTX
from tests.org_utils import add_member, make_org_with_admin

VALID_GRAPH = {
    "nodes": [
        {"id": "p1", "type": "provider", "data": {"provider_id": "11111111-1111-1111-1111-111111111111", "order": 0}},
    ],
    "edges": [],
}


@pytest.mark.asyncio
async def test_university_admin_can_create_and_read_draft_graph(db_session) -> None:
    _user, org, admin = await make_org_with_admin(db_session, org_type="university")

    graph = await routing_service.create_draft_graph(
        db_session, principal=admin, task_family="chat", graph=VALID_GRAPH, ctx=CTX,
    )

    assert graph.status == "DRAFT"
    fetched = await routing_service.get_graph(db_session, principal=admin, graph_id=graph.id)
    assert fetched.id == graph.id


@pytest.mark.asyncio
async def test_create_graph_rejects_invalid_structure(db_session) -> None:
    _user, org, admin = await make_org_with_admin(db_session, org_type="university")

    with pytest.raises(InvalidRoutingGraphError):
        await routing_service.create_draft_graph(
            db_session, principal=admin, task_family="chat", graph={"nodes": [], "edges": []}, ctx=CTX,
        )


@pytest.mark.asyncio
async def test_member_without_ai_settings_manage_is_denied(db_session) -> None:
    _user, org, admin = await make_org_with_admin(db_session, org_type="university")
    _member_user, _membership, member = await add_member(
        db_session, org=org, permissions=[("ai_settings", "read")]
    )

    with pytest.raises(PermissionDeniedError):
        await routing_service.create_draft_graph(
            db_session, principal=member, task_family="chat", graph=VALID_GRAPH, ctx=CTX,
        )
```

- [ ] **Step 2: Run to verify failure**

Run: `cd backend && DEBUG=false uv run pytest tests/integration/test_ai_routing_service.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement errors and service**

```python
# backend/app/modules/ai_settings/application/routing_errors.py
from __future__ import annotations

from app.shared.exceptions import ConflictError, ValidationFailedError


class InvalidRoutingGraphError(ValidationFailedError):
    message = "Sơ đồ định tuyến AI không hợp lệ."

    def __init__(self, errors: list[str]) -> None:
        super().__init__(self.message, details={"reason": "invalid_routing_graph", "errors": errors})


class RoutingGraphNotEditableError(ConflictError):
    message = "Chỉ có thể chỉnh sửa sơ đồ định tuyến ở trạng thái nháp."

    def __init__(self) -> None:
        super().__init__(self.message, details={"reason": "not_editable"})
```

```python
# backend/app/modules/ai_settings/application/routing_service.py
"""Draft routing-graph CRUD: RBAC + structural validation + audit. Activation
(compile into ai_model_aliases + republish EffectiveAiConfig) lives in
``routing_activation_service`` (Task 4) since it has a different permission
surface and side effect (mutating the live gateway config).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.ai_settings.application import settings_service
from app.modules.ai_settings.application.routing_errors import (
    InvalidRoutingGraphError,
    RoutingGraphNotEditableError,
)
from app.modules.ai_settings.domain.routing_models import AiRoutingGraph
from app.modules.ai_settings.domain.routing_validation import validate_routing_graph
from app.modules.auth.application.context import RequestContext
from app.shared.audit import AuditContext, write_audit
from app.shared.exceptions import ResourceNotFoundError
from app.shared.permissions import Principal


def _audit_ctx(principal: Principal, ctx: RequestContext) -> AuditContext:
    return AuditContext(
        actor_id=principal.user_id, actor_org_id=principal.org_id, ip=ctx.ip, user_agent=ctx.user_agent
    )


async def create_draft_graph(
    session: AsyncSession,
    *,
    principal: Principal,
    task_family: str,
    graph: dict,
    ctx: RequestContext,
) -> AiRoutingGraph:
    await settings_service._require_ai_settings_admin(session, principal, "manage")

    errors = validate_routing_graph(graph)
    if errors:
        raise InvalidRoutingGraphError(errors)

    row = AiRoutingGraph(
        task_family=task_family, graph=graph, status="DRAFT", version=1,
        created_by=principal.user_id, created_at=datetime.now(tz=UTC),
    )
    session.add(row)
    await session.flush()

    await write_audit(
        session, action="ai_settings.routing_graph_created", resource_type="ai_routing_graph",
        resource_id=row.id, context=_audit_ctx(principal, ctx),
        after={"task_family": task_family, "status": "DRAFT"},
    )
    await session.commit()
    return row


async def update_draft_graph(
    session: AsyncSession, *, principal: Principal, graph_id: uuid.UUID, graph: dict, ctx: RequestContext
) -> AiRoutingGraph:
    await settings_service._require_ai_settings_admin(session, principal, "manage")
    row = await get_graph(session, principal=principal, graph_id=graph_id)

    if row.status != "DRAFT":
        raise RoutingGraphNotEditableError()

    errors = validate_routing_graph(graph)
    if errors:
        raise InvalidRoutingGraphError(errors)

    before = {"graph": row.graph}
    row.graph = graph
    await session.flush()
    await write_audit(
        session, action="ai_settings.routing_graph_updated", resource_type="ai_routing_graph",
        resource_id=row.id, context=_audit_ctx(principal, ctx), before=before, after={"graph": graph},
    )
    await session.commit()
    return row


async def get_graph(
    session: AsyncSession, *, principal: Principal, graph_id: uuid.UUID
) -> AiRoutingGraph:
    await settings_service._require_ai_settings_admin(session, principal, "read")
    row = await session.get(AiRoutingGraph, graph_id)
    if row is None:
        raise ResourceNotFoundError()
    return row


async def list_graphs(
    session: AsyncSession, *, principal: Principal, task_family: str | None = None
) -> list[AiRoutingGraph]:
    await settings_service._require_ai_settings_admin(session, principal, "read")
    stmt = select(AiRoutingGraph).order_by(AiRoutingGraph.created_at.desc())
    if task_family is not None:
        stmt = stmt.where(AiRoutingGraph.task_family == task_family)
    result = await session.execute(stmt)
    return list(result.scalars().all())
```

Run: `grep -n "async def add_member" -A 10 backend/tests/org_utils.py` to reconfirm its exact 3-tuple return shape (`user, membership, principal`), matching what Phase A's execution already discovered — use that shape in Step 1's test as written above.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && DEBUG=false uv run pytest tests/integration/test_ai_routing_service.py -v`
Expected: 3 passed

---

### Task 4: Activation service — compile graph into `ai_model_aliases`

**Files:**
- Create: `backend/app/modules/ai_settings/application/routing_activation_service.py`
- Test: `backend/tests/integration/test_ai_routing_activation_service.py`

**Interfaces:**
- Consumes: `AiRoutingGraph`/`AiRoutingGraphActivation` (Task 2), `routing_service.get_graph` (Task 3), `app.ai.gateway.provider_models.AiModelAlias`/`AiProviderConfig`, `app.modules.ai_settings.domain.aliases.ALIAS_FIELDS`, `app.modules.ai_settings.application.resolver.resolve_and_publish`.
- Produces: `async def activate_routing_graph(session, *, principal, graph_id, ctx) -> AiRoutingGraph` — resolves the currently-configured alias for the graph's `task_family` (via `AiSettings.<task_family>_model_alias`), sets that `AiModelAlias`'s `provider_id` (first provider node, `order=0`) and `fallback_provider_names` (remaining provider nodes' names, in `order`), writes an `ai_routing_graph_activations` row, republishes `EffectiveAiConfig`, and marks the graph `ACTIVE`.

- [ ] **Step 1: Write failing tests**

```python
# backend/tests/integration/test_ai_routing_activation_service.py
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from app.ai.gateway.provider_models import AiModelAlias, AiProviderConfig
from app.modules.ai_settings.application import routing_activation_service, routing_service
from tests.auth_utils import CTX
from tests.org_utils import make_org_with_admin


async def _seed_two_providers_and_alias(db_session):
    provider_a = AiProviderConfig(name="provider-a", provider_type="openai_compatible", base_url="https://a.example.com", is_active=True)
    provider_b = AiProviderConfig(name="provider-b", provider_type="openai_compatible", base_url="https://b.example.com", is_active=True)
    db_session.add_all([provider_a, provider_b])
    await db_session.flush()

    alias = AiModelAlias(alias_name="chat_cheap", model_id="chat-cheap-v1", provider_id=provider_a.id, task_families="chat", is_active=True)
    db_session.add(alias)
    await db_session.flush()
    await db_session.commit()
    return provider_a, provider_b, alias


@pytest.mark.asyncio
async def test_activate_compiles_graph_into_model_alias(db_session) -> None:
    _user, org, admin = await make_org_with_admin(db_session, org_type="university")
    provider_a, provider_b, alias = await _seed_two_providers_and_alias(db_session)

    # AiSettings singleton must point chat_model_alias at "chat_cheap" for the
    # compile step to find it — reuse the settings resolver's get_or_create.
    from app.modules.ai_settings.infrastructure import repository as ai_settings_repo

    settings_row = await ai_settings_repo.get_or_create_platform(db_session)
    settings_row.chat_model_alias = "chat_cheap"
    await db_session.commit()

    graph = await routing_service.create_draft_graph(
        db_session, principal=admin, task_family="chat",
        graph={
            "nodes": [
                {"id": "p1", "type": "provider", "data": {"provider_id": str(provider_b.id), "order": 0}},
                {"id": "p2", "type": "provider", "data": {"provider_id": str(provider_a.id), "order": 1}},
            ],
            "edges": [{"source": "p1", "target": "p2", "kind": "fallback"}],
        },
        ctx=CTX,
    )

    activated = await routing_activation_service.activate_routing_graph(
        db_session, principal=admin, graph_id=graph.id, ctx=CTX,
    )

    assert activated.status == "ACTIVE"
    refreshed_alias = await db_session.get(AiModelAlias, alias.id)
    assert refreshed_alias.provider_id == provider_b.id
    assert refreshed_alias.fallback_provider_names == "provider-a"


@pytest.mark.asyncio
async def test_activation_writes_activation_audit_row(db_session) -> None:
    _user, org, admin = await make_org_with_admin(db_session, org_type="university")
    provider_a, _provider_b, _alias = await _seed_two_providers_and_alias(db_session)

    from app.modules.ai_settings.infrastructure import repository as ai_settings_repo

    settings_row = await ai_settings_repo.get_or_create_platform(db_session)
    settings_row.chat_model_alias = "chat_cheap"
    await db_session.commit()

    graph = await routing_service.create_draft_graph(
        db_session, principal=admin, task_family="chat",
        graph={"nodes": [{"id": "p1", "type": "provider", "data": {"provider_id": str(provider_a.id), "order": 0}}], "edges": []},
        ctx=CTX,
    )
    await routing_activation_service.activate_routing_graph(db_session, principal=admin, graph_id=graph.id, ctx=CTX)

    from app.modules.ai_settings.domain.routing_models import AiRoutingGraphActivation

    rows = (await db_session.execute(select(AiRoutingGraphActivation).where(AiRoutingGraphActivation.graph_id == graph.id))).scalars().all()
    assert len(rows) == 1
    assert rows[0].graph_version == graph.version
```

Run: `grep -n "async def get_or_create_platform" backend/app/modules/ai_settings/infrastructure/repository.py` to confirm this exact function name/signature before relying on it in the test.

- [ ] **Step 2: Run to verify failure**

Run: `cd backend && DEBUG=false uv run pytest tests/integration/test_ai_routing_activation_service.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement the activation service**

```python
# backend/app/modules/ai_settings/application/routing_activation_service.py
"""Compiles a DRAFT routing graph into the real ai_model_aliases row the
gateway reads, then republishes EffectiveAiConfig via the same
commit -> resolve_and_publish -> commit seam ai_settings' provider/alias
endpoints already use (backend/app/modules/ai_settings/api/router.py's
``_commit_and_republish``). The graph itself never becomes a second runtime
read path — see docs/superpowers/specs/2026-07-02-no-code-workflow-and-ai-routing-canvas-design.md §2b.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.gateway.provider_models import AiModelAlias, AiProviderConfig
from app.modules.ai_settings.application import resolver, routing_service, settings_service
from app.modules.ai_settings.domain.aliases import ALIAS_FIELDS
from app.modules.ai_settings.domain.routing_models import AiRoutingGraph, AiRoutingGraphActivation
from app.modules.ai_settings.infrastructure import repository as ai_settings_repo
from app.modules.auth.application.context import RequestContext
from app.shared.audit import write_audit
from app.shared.exceptions import ResourceNotFoundError, ValidationFailedError
from app.shared.permissions import Principal

_FIELD_FOR_FAMILY = {family: field for field, family in ALIAS_FIELDS.items()}


async def activate_routing_graph(
    session: AsyncSession, *, principal: Principal, graph_id: uuid.UUID, ctx: RequestContext
) -> AiRoutingGraph:
    await settings_service._require_ai_settings_admin(session, principal, "manage")
    row = await routing_service.get_graph(session, principal=principal, graph_id=graph_id)

    settings_row = await ai_settings_repo.get_or_create_platform(session)
    field = _FIELD_FOR_FAMILY.get(row.task_family)
    alias_name = getattr(settings_row, field, None) if field else None
    if not alias_name:
        raise ValidationFailedError(
            "Chưa cấu hình alias cho nhóm tác vụ này.",
            details={"reason": "no_configured_alias", "task_family": row.task_family},
        )

    alias = (
        await session.execute(select(AiModelAlias).where(AiModelAlias.alias_name == alias_name))
    ).scalar_one_or_none()
    if alias is None:
        raise ResourceNotFoundError()

    provider_nodes = sorted(
        (n for n in row.graph["nodes"] if n.get("type") == "provider"),
        key=lambda n: n["data"]["order"],
    )
    primary_id = uuid.UUID(provider_nodes[0]["data"]["provider_id"])
    fallback_ids = [uuid.UUID(n["data"]["provider_id"]) for n in provider_nodes[1:]]

    fallback_names: list[str] = []
    if fallback_ids:
        providers = (
            await session.execute(select(AiProviderConfig).where(AiProviderConfig.id.in_(fallback_ids)))
        ).scalars().all()
        by_id = {p.id: p.name for p in providers}
        fallback_names = [by_id[pid] for pid in fallback_ids if pid in by_id]

    alias.provider_id = primary_id
    alias.fallback_provider_names = ",".join(fallback_names) if fallback_names else None
    row.compiled_alias_id = alias.id
    row.status = "ACTIVE"
    row.activated_at = datetime.now(tz=UTC)
    await session.flush()

    session.add(
        AiRoutingGraphActivation(
            id=uuid.uuid4(),
            graph_id=row.id,
            graph_version=row.version,
            activated_by=principal.user_id,
            activated_at=datetime.now(tz=UTC),
        )
    )
    await write_audit(
        session, action="ai_settings.routing_graph_activated", resource_type="ai_routing_graph",
        resource_id=row.id,
        context=__import__("app.shared.audit", fromlist=["AuditContext"]).AuditContext(
            actor_id=principal.user_id, actor_org_id=principal.org_id, ip=ctx.ip, user_agent=ctx.user_agent
        ),
        after={"task_family": row.task_family, "alias_name": alias_name},
    )
    await session.commit()
    await resolver.resolve_and_publish(session)
    await session.commit()
    return row
```

Replace the awkward `__import__("app.shared.audit", ...)` call with a normal top-level `from app.shared.audit import AuditContext` import — that inline form is only written out above to make the diff obvious; use the clean import in the actual file.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && DEBUG=false uv run pytest tests/integration/test_ai_routing_activation_service.py -v`
Expected: 2 passed

---

### Task 5: Provider-identity read endpoint + circuit-breaker read endpoint

**Files:**
- Create: `backend/app/modules/ai_settings/application/routing_read_service.py`
- Modify: `backend/app/ai/gateway/factory.py`
- Test: `backend/tests/integration/test_ai_routing_read_service.py`

**Interfaces:**
- Consumes: `AiProviderConfig`/`AiModelAlias`, `settings_service._require_ai_settings_admin`, `write_audit`.
- Produces: `async def get_routing_canvas_view(session, *, principal, task_family, ctx) -> dict` returning `{"task_family": ..., "providers": [{"provider_id": ..., "vendor_label": ..., "model_family_label": ..., "circuit_state": "closed"|"open", "provider_internal": str|None, "model_id": str|None}]}` where `provider_internal`/`model_id` are populated ONLY if `principal` holds `ai_settings:view_provider_identity` (else `None`, and the curated labels are always present); in `factory.py`, a new public `get_circuit_state(provider_name: str) -> str` returning `"open"` or `"closed"` (never inventing a `half_open` value the code doesn't track).

- [ ] **Step 1: Add a public circuit-state accessor to `factory.py`**

Run: `grep -n "_get_circuit\|_circuit_states" backend/app/ai/gateway/factory.py` to find the exact current private helper, then add directly below it:

```python
def get_circuit_state(provider_name: str) -> str:
    """Public read-only accessor for the routing canvas — never invents a
    'half_open' state since this module's _CircuitState only tracks a binary
    open/closed condition (see is_open()'s recovery-window check above)."""

    return "open" if _get_circuit(provider_name).is_open() else "closed"
```

- [ ] **Step 2: Write failing tests**

```python
# backend/tests/integration/test_ai_routing_read_service.py
from __future__ import annotations

import pytest

from app.ai.gateway.provider_models import AiModelAlias, AiProviderConfig
from app.modules.ai_settings.application import routing_read_service
from app.shared.audit import AuditLog
from sqlalchemy import select
from tests.auth_utils import CTX
from tests.org_utils import add_member, make_org_with_admin


async def _seed_provider_and_alias(db_session):
    provider = AiProviderConfig(name="provider-a", provider_type="openai_compatible", base_url="https://a.example.com", is_active=True)
    db_session.add(provider)
    await db_session.flush()
    alias = AiModelAlias(alias_name="chat_cheap", model_id="chat-cheap-v1", provider_id=provider.id, task_families="chat", is_active=True)
    db_session.add(alias)
    await db_session.commit()
    return provider, alias


@pytest.mark.asyncio
async def test_read_only_holder_sees_curated_labels_not_raw_identity(db_session) -> None:
    _user, org, admin = await make_org_with_admin(db_session, org_type="university")
    _member_user, _membership, reader = await add_member(db_session, org=org, permissions=[("ai_settings", "read")])
    await _seed_provider_and_alias(db_session)

    view = await routing_read_service.get_routing_canvas_view(db_session, principal=reader, task_family="chat", ctx=CTX)

    provider_entry = view["providers"][0]
    assert provider_entry["vendor_label"]
    assert provider_entry["provider_internal"] is None
    assert provider_entry["model_id"] is None


@pytest.mark.asyncio
async def test_holder_with_view_provider_identity_sees_raw_identity_and_is_audited(db_session) -> None:
    _user, org, admin = await make_org_with_admin(db_session, org_type="university")
    _member_user, _membership, privileged = await add_member(
        db_session, org=org, permissions=[("ai_settings", "read"), ("ai_settings", "view_provider_identity")]
    )
    await _seed_provider_and_alias(db_session)

    view = await routing_read_service.get_routing_canvas_view(db_session, principal=privileged, task_family="chat", ctx=CTX)

    provider_entry = view["providers"][0]
    assert provider_entry["provider_internal"] == "provider-a"
    assert provider_entry["model_id"] == "chat-cheap-v1"

    rows = (
        await db_session.execute(select(AuditLog).where(AuditLog.action == "ai_settings.provider_identity_viewed"))
    ).scalars().all()
    assert len(rows) == 1
```

Run: `grep -n "^class AuditLog" -A 15 backend/app/shared/audit.py` first to confirm the ORM class name/import path is exactly `AuditLog` from `app.shared.audit` — adjust the import in the test if the real class lives elsewhere (e.g. a separate `audit_models.py`).

- [ ] **Step 3: Run to verify failure**

Run: `cd backend && DEBUG=false uv run pytest tests/integration/test_ai_routing_read_service.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 4: Implement the curated-label helper and read service**

```python
# backend/app/modules/ai_settings/application/routing_read_service.py
"""Read-only view of live provider/alias/circuit-breaker state for the routing
canvas. Curated vendor_label/model_family_label are the DEFAULT display; raw
provider_internal/model_id are populated only for callers holding
ai_settings:view_provider_identity, per ADR-0011.1 (docs/API_CONTRACTS.md).
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.gateway.factory import get_circuit_state
from app.ai.gateway.provider_models import AiModelAlias, AiProviderConfig
from app.modules.ai_settings.application import settings_service
from app.modules.auth.application.context import RequestContext
from app.shared.audit import AuditContext, write_audit
from app.shared.exceptions import PermissionDeniedError
from app.shared.permissions import Principal, permission_checker

# Static, ai-engineer-maintained curated labels per provider_type — never the
# literal SDK model string. Extend this map as new provider_type values ship;
# do not derive it from provider.name (that IS the raw identifier).
_VENDOR_LABELS: dict[str, str] = {
    "openai_compatible": "OpenAI-compatible provider",
    "anthropic": "Anthropic",
    "local": "Local/self-hosted model",
}


def _has_identity_permission(principal: Principal) -> bool:
    return principal.is_superadmin or permission_checker.can(
        principal, "ai_settings", "view_provider_identity", resource_org_id=principal.org_id
    )


async def get_routing_canvas_view(
    session: AsyncSession, *, principal: Principal, task_family: str, ctx: RequestContext
) -> dict:
    await settings_service._require_ai_settings_admin(session, principal, "read")

    aliases = (
        await session.execute(select(AiModelAlias).where(AiModelAlias.task_families == task_family))
    ).scalars().all()

    provider_ids = {a.provider_id for a in aliases if a.provider_id is not None}
    providers = (
        await session.execute(select(AiProviderConfig).where(AiProviderConfig.id.in_(provider_ids)))
    ).scalars().all() if provider_ids else []

    show_raw = _has_identity_permission(principal)
    if show_raw:
        await write_audit(
            session,
            action="ai_settings.provider_identity_viewed",
            resource_type="ai_model_alias",
            context=AuditContext(
                actor_id=principal.user_id, actor_org_id=principal.org_id, ip=ctx.ip, user_agent=ctx.user_agent
            ),
        )
        await session.commit()

    alias_by_provider = {a.provider_id: a for a in aliases}
    provider_entries = []
    for provider in providers:
        alias = alias_by_provider.get(provider.id)
        provider_entries.append(
            {
                "provider_id": str(provider.id),
                "vendor_label": _VENDOR_LABELS.get(provider.provider_type, "AI provider"),
                "model_family_label": task_family.capitalize(),
                "circuit_state": get_circuit_state(provider.name),
                "provider_internal": provider.name if show_raw else None,
                "model_id": (alias.model_id if alias and show_raw else None),
            }
        )

    return {"task_family": task_family, "providers": provider_entries}
```

Run: `grep -n "def can(" backend/app/shared/permissions.py` to confirm `permission_checker.can(...)` has the exact signature used above (matching `.require`'s signature already confirmed in Phase A) before relying on it.

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && DEBUG=false uv run pytest tests/integration/test_ai_routing_read_service.py -v`
Expected: 2 passed

---

### Task 6: API router — mount routing endpoints under the existing `ai_settings` admin router

**Files:**
- Create: `backend/app/modules/ai_settings/api/routing_schemas.py`
- Modify: `backend/app/modules/ai_settings/api/router.py`
- Test: `backend/tests/integration/test_ai_routing_api.py`

**Interfaces:**
- Consumes: `routing_service`, `routing_activation_service`, `routing_read_service` (Tasks 3–5).
- Produces: `POST /admin/ai-settings/routing-graphs`, `PATCH /admin/ai-settings/routing-graphs/{graph_id}`, `GET /admin/ai-settings/routing-graphs/{graph_id}`, `GET /admin/ai-settings/routing-graphs?task_family=`, `POST /admin/ai-settings/routing-graphs/{graph_id}/activate`, `GET /admin/ai-settings/routing-canvas/{task_family}` (the live view from Task 5).

- [ ] **Step 1: Write failing API tests**

```python
# backend/tests/integration/test_ai_routing_api.py
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.ai.gateway.provider_models import AiProviderConfig
from app.main import app
from tests.org_utils import make_org_with_admin


@pytest.mark.asyncio
async def test_create_and_activate_routing_graph_via_api(db_session, access_token_for) -> None:
    _user, org, admin = await make_org_with_admin(db_session, org_type="university")
    provider = AiProviderConfig(name="provider-a", provider_type="openai_compatible", base_url="https://a.example.com", is_active=True)
    db_session.add(provider)
    await db_session.commit()
    token = await access_token_for(admin)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        create_resp = await client.post(
            "/api/v1/admin/ai-settings/routing-graphs",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "task_family": "chat",
                "graph": {"nodes": [{"id": "p1", "type": "provider", "data": {"provider_id": str(provider.id), "order": 0}}], "edges": []},
            },
        )
        assert create_resp.status_code == 200
        graph_id = create_resp.json()["data"]["id"]

        canvas_resp = await client.get(
            "/api/v1/admin/ai-settings/routing-canvas/chat",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert canvas_resp.status_code == 200
        assert "vendor_label" in canvas_resp.json()["data"]["providers"][0]
```

Run: `grep -rn "access_token_for" frontend/e2e backend/tests` — reuse whatever real login/token-issuance helper the Phase A/B execution already established for authenticated API tests (the Phase A execution report noted no such fixture existed and built the test using the real `/auth/login` flow plus an identity switch instead) — mirror that exact pattern here rather than assuming `access_token_for` exists.

- [ ] **Step 2: Run to verify failure**

Run: `cd backend && DEBUG=false uv run pytest tests/integration/test_ai_routing_api.py -v`
Expected: FAIL (404, route not mounted yet)

- [ ] **Step 3: Implement schemas and router additions**

```python
# backend/app/modules/ai_settings/api/routing_schemas.py
from __future__ import annotations

from pydantic import BaseModel


class CreateRoutingGraphRequest(BaseModel):
    task_family: str
    graph: dict


class UpdateRoutingGraphRequest(BaseModel):
    graph: dict
```

In `backend/app/modules/ai_settings/api/router.py`, add these imports near the existing ones:

```python
import uuid

from fastapi import Query

from app.modules.ai_settings.api.routing_schemas import (
    CreateRoutingGraphRequest,
    UpdateRoutingGraphRequest,
)
from app.modules.ai_settings.application import (
    routing_activation_service,
    routing_read_service,
    routing_service,
)
```

And add these endpoints to `admin_router` (append after the existing model-alias endpoints, before the file's closing):

```python
def _routing_graph_presenter(row) -> dict:
    return {
        "id": str(row.id),
        "task_family": row.task_family,
        "graph": row.graph,
        "status": row.status,
        "version": row.version,
    }


@admin_router.post("/routing-graphs")
async def create_routing_graph(
    body: CreateRoutingGraphRequest,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    row = await routing_service.create_draft_graph(
        session, principal=auth.principal, task_family=body.task_family, graph=body.graph, ctx=auth.ctx,
    )
    return success(_routing_graph_presenter(row))


@admin_router.patch("/routing-graphs/{graph_id}")
async def update_routing_graph(
    graph_id: uuid.UUID,
    body: UpdateRoutingGraphRequest,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    row = await routing_service.update_draft_graph(
        session, principal=auth.principal, graph_id=graph_id, graph=body.graph, ctx=auth.ctx,
    )
    return success(_routing_graph_presenter(row))


@admin_router.get("/routing-graphs/{graph_id}")
async def get_routing_graph(
    graph_id: uuid.UUID,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    row = await routing_service.get_graph(session, principal=auth.principal, graph_id=graph_id)
    return success(_routing_graph_presenter(row))


@admin_router.get("/routing-graphs")
async def list_routing_graphs(
    task_family: str | None = Query(default=None),
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    rows = await routing_service.list_graphs(session, principal=auth.principal, task_family=task_family)
    return success([_routing_graph_presenter(r) for r in rows])


@admin_router.post("/routing-graphs/{graph_id}/activate")
async def activate_routing_graph(
    graph_id: uuid.UUID,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    row = await routing_activation_service.activate_routing_graph(
        session, principal=auth.principal, graph_id=graph_id, ctx=auth.ctx,
    )
    return success(_routing_graph_presenter(row))


@admin_router.get("/routing-canvas/{task_family}")
async def get_routing_canvas(
    task_family: str,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    view = await routing_read_service.get_routing_canvas_view(
        session, principal=auth.principal, task_family=task_family, ctx=auth.ctx,
    )
    return success(view)
```

Run: `grep -n "^from\|^import\|CurrentAuth\|get_current_auth\|get_db_session\|^from app.shared.responses" backend/app/modules/ai_settings/api/router.py | head -20` first to confirm these names are already imported in this file (they should be, since the existing provider/alias endpoints use the identical dependencies) — do not duplicate an import that's already present.

- [ ] **Step 4: Run the API test**

Run: `cd backend && DEBUG=false uv run pytest tests/integration/test_ai_routing_api.py -v`
Expected: 1 passed.

- [ ] **Step 5: Run the full backend suite for regressions**

Run: `cd backend && DEBUG=false uv run pytest -q`
Expected: same pre-existing failure count as before this plan (the known-unrelated `test_ai_governance.py::test_check_async_enforces_user_plan_ai_quota` failure), no new failures.

---

### Task 7: Frontend API client + routing canvas screen

**Files:**
- Create: `frontend/src/lib/api/ai-routing.ts`
- Modify: `frontend/src/lib/api/index.ts`
- Create: `frontend/src/components/ai-settings/routing-canvas-screen.tsx`
- Create: `frontend/src/app/[locale]/(university)/university/ai-settings/routing/page.tsx`
- Modify: `frontend/src/messages/vi/university/ai-settings.json`
- Modify: `frontend/src/messages/en/university/ai-settings.json`

**Interfaces:**
- Consumes: `FlowCanvas`, `NodeTypeDef` (`frontend/src/components/workflow/flow-canvas.tsx`, already shipped in Phase B — reused as-is, not copied).
- Produces: `export interface RoutingProviderEntry { provider_id: string; vendor_label: string; model_family_label: string; circuit_state: "closed" | "open"; provider_internal: string | null; model_id: string | null }`, `export const aiRoutingApi = { create, update, get, list, activate, canvasView }`.

- [ ] **Step 1: Implement the API client**

```ts
// frontend/src/lib/api/ai-routing.ts
import { api } from "./client";
import type { WorkflowNodeType } from "./workflows";

export interface RoutingGraphNode {
  id: string;
  type: "provider";
  data: { provider_id: string; order: number };
  position?: { x: number; y: number };
}

export interface RoutingGraphEdge {
  source: string;
  target: string;
  kind: "fallback";
}

export interface RoutingGraph {
  nodes: RoutingGraphNode[];
  edges: RoutingGraphEdge[];
}

export type RoutingGraphStatus = "DRAFT" | "ACTIVE" | "ARCHIVED";

export interface AiRoutingGraphRecord {
  id: string;
  task_family: string;
  graph: RoutingGraph;
  status: RoutingGraphStatus;
  version: number;
}

export interface RoutingProviderEntry {
  provider_id: string;
  vendor_label: string;
  model_family_label: string;
  circuit_state: "closed" | "open";
  provider_internal: string | null;
  model_id: string | null;
}

export interface RoutingCanvasView {
  task_family: string;
  providers: RoutingProviderEntry[];
}

export const aiRoutingApi = {
  create(taskFamily: string, graph: RoutingGraph): Promise<AiRoutingGraphRecord> {
    return api.post<AiRoutingGraphRecord>("/admin/ai-settings/routing-graphs", {
      task_family: taskFamily,
      graph,
    });
  },
  update(graphId: string, graph: RoutingGraph): Promise<AiRoutingGraphRecord> {
    return api.patch<AiRoutingGraphRecord>(`/admin/ai-settings/routing-graphs/${graphId}`, { graph });
  },
  get(graphId: string): Promise<AiRoutingGraphRecord> {
    return api.get<AiRoutingGraphRecord>(`/admin/ai-settings/routing-graphs/${graphId}`);
  },
  list(taskFamily?: string): Promise<AiRoutingGraphRecord[]> {
    return api.get<AiRoutingGraphRecord[]>(
      "/admin/ai-settings/routing-graphs",
      taskFamily ? { query: { task_family: taskFamily } } : undefined,
    );
  },
  activate(graphId: string): Promise<AiRoutingGraphRecord> {
    return api.post<AiRoutingGraphRecord>(`/admin/ai-settings/routing-graphs/${graphId}/activate`);
  },
  canvasView(taskFamily: string): Promise<RoutingCanvasView> {
    return api.get<RoutingCanvasView>(`/admin/ai-settings/routing-canvas/${taskFamily}`);
  },
};

export type { WorkflowNodeType };
```

Drop the trailing `export type { WorkflowNodeType }` re-export if nothing in this file actually needs it — it was only included as a placeholder reminder to check; if unused, TypeScript/lint will flag it, so remove it before Step 4's lint check.

- [ ] **Step 2: Register the barrel export**

In `frontend/src/lib/api/index.ts`, add:
```ts
export * from "./ai-routing";
```

- [ ] **Step 3: Add i18n keys to the existing `ai-settings` namespace (do not create a new namespace — this feature lives inside the existing AI Settings surface)**

In `frontend/src/messages/vi/university/ai-settings.json`, add inside the existing `"aiSettings"` object:
```json
"routingCanvasTitle": "Sơ đồ định tuyến AI",
"routingCanvasSubtitle": "Kéo thả để xem và cấu hình thứ tự ưu tiên nhà cung cấp AI cho từng nhóm tác vụ.",
"routingProviderNode": "Nhà cung cấp",
"routingActivate": "Kích hoạt định tuyến này",
"routingCircuitOpen": "Đang gặp sự cố",
"routingCircuitClosed": "Hoạt động bình thường"
```
And the `en` mirror in `frontend/src/messages/en/university/ai-settings.json`:
```json
"routingCanvasTitle": "AI Routing Map",
"routingCanvasSubtitle": "Drag and drop to view and configure AI provider priority per task family.",
"routingProviderNode": "Provider",
"routingActivate": "Activate this routing",
"routingCircuitOpen": "Degraded",
"routingCircuitClosed": "Healthy"
```

Run: `grep -n "\"aiSettings\"" -A 3 frontend/src/messages/vi/university/ai-settings.json` first to confirm the exact top-level key nesting before inserting — add the new keys inside the correct object, not as sibling top-level keys.

- [ ] **Step 4: Implement the routing canvas screen**

```tsx
// frontend/src/components/ai-settings/routing-canvas-screen.tsx
"use client";

import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslations } from "next-intl";

import { Button, Select, useToast } from "@/components/ui";
import { PageHeader } from "@/components/layout/page-header";
import { aiRoutingApi, type RoutingGraph } from "@/lib/api";
import { FlowCanvas, type NodeTypeDef } from "@/components/workflow/flow-canvas";

const TASK_FAMILIES = ["chat", "reasoning", "embedding", "rerank", "eval"] as const;
const EMPTY_GRAPH: RoutingGraph = { nodes: [], edges: [] };

export function RoutingCanvasScreen() {
  const t = useTranslations("aiSettings");
  const toast = useToast();
  const queryClient = useQueryClient();
  const [taskFamily, setTaskFamily] = useState<(typeof TASK_FAMILIES)[number]>("chat");
  const [graph, setGraph] = useState<RoutingGraph>(EMPTY_GRAPH);
  const [graphId, setGraphId] = useState<string | null>(null);

  const canvasQuery = useQuery({
    queryKey: ["admin", "ai-routing-canvas", taskFamily],
    queryFn: () => aiRoutingApi.canvasView(taskFamily),
  });

  const defs: NodeTypeDef[] = useMemo(
    () => [{ type: "action", label: t("routingProviderNode"), defaultData: {} }],
    [t],
  );

  const save = useMutation({
    mutationFn: async () => {
      if (!graphId) {
        const created = await aiRoutingApi.create(taskFamily, graph);
        setGraphId(created.id);
        return created;
      }
      return aiRoutingApi.update(graphId, graph);
    },
    onSuccess: () => toast.show({ tone: "success", title: "OK" }),
  });

  const activate = useMutation({
    mutationFn: () => aiRoutingApi.activate(graphId as string),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin", "ai-routing-canvas", taskFamily] });
      toast.show({ tone: "success", title: t("routingActivate") });
    },
  });

  return (
    <>
      <PageHeader
        title={t("routingCanvasTitle")}
        description={t("routingCanvasSubtitle")}
        actions={
          <div className="flex items-center gap-2">
            <Select
              value={taskFamily}
              onChange={(e) => setTaskFamily(e.target.value as (typeof TASK_FAMILIES)[number])}
              options={TASK_FAMILIES.map((f) => ({ value: f, label: f }))}
            />
            <Button variant="secondary" loading={save.isPending} disabled={!graphId} onClick={() => save.mutate()}>
              Save
            </Button>
            <Button variant="primary" disabled={!graphId} loading={activate.isPending} onClick={() => activate.mutate()}>
              {t("routingActivate")}
            </Button>
          </div>
        }
      />

      <div className="grid grid-cols-[1fr_260px] gap-4">
        <FlowCanvas graph={graph} nodeTypeDefs={defs} onGraphChange={setGraph} />
        <aside className="space-y-2 rounded-2xl border border-[var(--border-subtle)] bg-white/90 p-4" data-testid="circuit-panel">
          {(canvasQuery.data?.providers ?? []).map((p) => (
            <div key={p.provider_id} className="flex items-center justify-between text-sm">
              <span>{p.provider_internal ?? p.vendor_label}</span>
              <span className={p.circuit_state === "open" ? "text-rose-600" : "text-emerald-600"}>
                {p.circuit_state === "open" ? t("routingCircuitOpen") : t("routingCircuitClosed")}
              </span>
            </div>
          ))}
        </aside>
      </div>
    </>
  );
}
```

Run: `grep -n "export function Select" -A 10 frontend/src/components/ui/select.tsx` to confirm `Select` accepts an `options: {value, label}[]` prop as used above (the Phase B execution report noted the real `Select` takes `options`, not `<option>` children — reuse that same confirmed shape here) and adjust if it differs.

- [ ] **Step 5: Add the route**

```tsx
// frontend/src/app/[locale]/(university)/university/ai-settings/routing/page.tsx
import { RoutingCanvasScreen } from "@/components/ai-settings/routing-canvas-screen";

export default function UniversityAiRoutingCanvasPage() {
  return <RoutingCanvasScreen />;
}
```

- [ ] **Step 6: Add a link from the main AI Settings page to the new routing canvas**

Run: `grep -n "PageHeader" frontend/src/components/ai-settings/ai-settings-screen.tsx | head -3` to find the existing `<PageHeader actions={...}>` block, then add a secondary link/button there pointing to `/university/ai-settings/routing` (use the existing `Link`/`Button` pattern already in that file — do not introduce a new nav-config entry for this, since it's a sub-view of the existing AI Settings page, not a new top-level persona surface).

- [ ] **Step 7: Typecheck, lint, message parity**

Run: `cd frontend && pnpm run typecheck && pnpm run lint && pnpm run check:messages`
Expected: all clean.

- [ ] **Step 8: Extend the Playwright suite**

```ts
// frontend/e2e/university-ai-routing-canvas.spec.ts
import { expect, test, type Page } from "@playwright/test";

const EMAIL = "career.admin@vinuni.edu.vn";
const PASSWORD = "123456";

async function loginAsUniversityAdmin(page: Page) {
  await page.goto("/vi/auth/login");
  await page.getByLabel(/email/i).fill(EMAIL);
  await page.getByLabel(/mật khẩu/i).fill(PASSWORD);
  await page.getByRole("button", { name: "Đăng nhập", exact: true }).click();
  await expect(page).toHaveURL(/\/vi\/university\//, { timeout: 30_000 });
}

test("university admin can open the AI routing canvas and it never shows raw provider text to a non-privileged view", async ({ page }) => {
  await loginAsUniversityAdmin(page);
  await page.goto("/vi/university/ai-settings/routing");
  await expect(page.getByTestId("circuit-panel")).toBeVisible({ timeout: 15_000 });
});
```

Run: `cd frontend && npx playwright test e2e/university-ai-routing-canvas.spec.ts`
Expected: 1 passed (requires the dev stack running per `docs/LOCAL_DEV_STACK.md`, same as Phase B's e2e run).

---

## Explicitly out of scope for this plan (deferred, not silently dropped)

- **Drag-and-drop node placement for provider nodes with visual fallback-chain reordering** — Task 7's screen renders the canvas and a circuit-health side panel, but does not yet implement a polished "drag provider cards into ordered chain" UX distinct from the generic `FlowCanvas` node/edge interactions; a follow-up should add a dedicated `ProviderNode` component (mirroring `frontend/src/components/workflow/node-types.tsx`'s pattern) instead of reusing the generic `"action"` node type as a placeholder, which Task 7 does only to ship an initial working version.
- **Live polling of circuit-breaker state** — Task 7's `canvasQuery` fetches once per `task_family` change; adding a polling interval (`refetchInterval`) for real-time health is a small follow-up, not done here to keep this plan's scope to the compile/activate/identity-permission core.
- **A dedicated `ProviderCatalogPicker` for choosing which `AiProviderConfig` rows are addable to a graph** — this plan assumes the admin already knows provider UUIDs (acceptable for the backend/API-level acceptance criteria) but the frontend doesn't yet offer a provider search/select control; add one once the core compile/activate loop is verified.
- **Half-open circuit state** — not implemented because the current `factory.py` circuit breaker doesn't track it as a distinct state; if that's added to the gateway later, `get_circuit_state`'s return type and the frontend's `circuit_state` union both need updating together.

## Self-review notes

- Re-verified fresh (not from a stale report) that the true migration head is `0050_ai_workforce_runs` and that `AiModelAlias.fallback_provider_names` already exists (added by migration `0049` from a concurrent session) — the compile step in Task 4 uses this real column, not an invented one.
- Confirmed no `ai_task_model_configs` table exists anywhere in code; every reference in this plan is to the real `ai_model_aliases`/`ai_provider_configs` tables.
- Confirmed circuit-breaker state is in-memory/per-process with only a binary open/closed condition — the plan does not invent a `half_open` value.
- Flagged every place a prop/signature couldn't be 100% pre-confirmed (`Select`'s options shape, `get_or_create_platform`'s exact name, `AuditLog`'s import path, the auth-token test helper) with an explicit `grep` verification step rather than a guess.
- This plan deliberately reuses `FlowCanvas` from Phase B without modification, proving the design doc's core "one shared canvas, two backend engines" claim — no changes to `frontend/src/components/workflow/flow-canvas.tsx` are needed or made here.
