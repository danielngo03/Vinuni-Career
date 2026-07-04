# No-Code/Low-Code Admin Canvas: Account Approval Workflows + AI Provider Routing

Status: Approved by product owner (user), 2026-07-02. Ready for implementation planning.

## 1. Problem

University admins currently configure two things through forms + on/off toggles:

1. Account approval rules (student verification, employer/partner approval) — no visual way to see or build conditional routing (if/else → department queue, named staff, auto-approve, email).
2. AI provider/model routing (which provider/model serves which task family, fallback chains, rotation) — `ai_settings` is CRUD-only, no visual picture of "what's calling what."

The user wants both to feel like drag-and-drop, connect-the-nodes tooling in "a real large system" (n8n/Zapier-like), not more forms.

## 2. Scope decision

Two features, two backend execution engines, **one shared frontend canvas component**.

### 2a. Account Approval Workflow Builder — extends already-planned E23 (docs/BACKLOG.md, docs/ARCHITECTURE.md L941-996, docs/BUSINESS_LOGIC.md §16)

This was already fully designed pre-reset, just not built. Decision: **build now** (product owner explicitly chose to pull this ahead of the currently-documented next priority — Discovery/Ads Rescue, CV contract completion, async worker fix — accepting those slip).

Phased build:

- **Phase A — engine only, no canvas.** `workflow_flows` / `workflow_executions` tables, Celery `execute_flow`, node types Trigger/Condition/Human Review/Action/Delay/End (no AI Process yet). Flows authored via seed/JSON initially. Ship exactly 2 templates: **student verification** and **partner/employer account approval**. Human Review node gains an `assignee_mode` field (`person` | `queue`) with `assignee_user_id` or `assignee_department_id`, resolved through the existing `organization` RBAC/membership system — never a hardcoded role or user ID in flow JSON (CLAUDE.md: "do not hardcode university staff roles"). SLA breach escalates: `person` mode → escalate to that person's manager/fallback queue; `queue` mode → broaden to a wider queue or department head.
- **Phase B — canvas frontend.** React Flow admin canvas: node palette, save/load JSON graph, DRAFT→TEST→ACTIVE, dry-run with sample data + node highlighting, execution history view, failed-execution inspector + replay, versioning (edit creates new version; cannot edit an ACTIVE version in place — already a hard rule in `.claude/rules/realtime.md`).
- **Phase C — AI Process node.** Adds an AI-assisted step (e.g., fraud-score) into approval flows, referencing an AI alias string only (e.g. `"chat_default"`) — never reaches into the AI routing graph's internals directly.

RBAC: `workflow:create` (draft) and `workflow:activate` (go live) as separate grantable permissions, so drafting and activation can be split across roles. Activating a flow that touches `student_registered`/`partner_registered` triggers requires explicit confirmation showing what changes. Max 100 concurrent executions/flow, FIFO queue to 10k, idempotent per trigger-event+flow_id — unchanged from docs/BUSINESS_LOGIC.md §16.

### 2b. AI Provider/Model Routing Canvas — new, owned by `ai_settings`, NOT the workflow engine

Rejected: modeling AI routing as a `workflow_flows` row / running it through `execute_flow`. Routing is a synchronous, per-request, in-memory config lookup (ADR-0011's `EffectiveAiConfig`); the workflow engine is async/Celery with multi-day human-review semantics. Forcing one into the other adds latency and wrong failure semantics.

Decision: new tables owned by `ai_settings`:

```
ai_routing_graphs            (id, task_family, graph JSONB, status DRAFT|ACTIVE|ARCHIVED,
                               version, created_by, created_at, activated_at,
                               compiled_config_id → ai_task_model_configs)
ai_routing_graph_activations (id, graph_id, graph_version, activated_by, activated_at,
                               previous_active_graph_id)   -- append-only audit trail
```

The graph is an **authoring/editing artifact**. On "Activate," it compiles into rows of the existing `ai_task_model_configs` table — the same table the gateway resolver already reads via the ADR-0011 `EffectiveAiConfig` snapshot. The gateway's hot-path read is untouched.

Node types: Provider/Model node, Fallback Chain edge (ordered), Condition edge (same `{{variable}}` expression style as workflow Condition nodes), Circuit Breaker annotation node (read-only, live state via polling/WebSocket — not execution logs).

Frontend: shared `FlowCanvas` component (React Flow wrapper: rendering, drag/drop, edge drawing, node palette panel, zoom/pan, node inspector, save/version chrome), parameterized by `flowKind: "account_approval" | "ai_routing"` selecting node palette + API adapter. Backend semantics, execution/state layers, and node-type registries are NOT shared between the two `flowKind`s.

Module boundary: `ai_settings` owns `ai_routing_graphs`/activations/compile-step/circuit-breaker-read-endpoint. `workflow` owns `workflow_flows`/`workflow_executions`/`execute_flow`, unchanged. Neither reads the other's tables directly — `workflow`'s future AI Process node references an alias string only.

### 2c. Provider identity visibility (ADR-0011.1 — already written into docs)

Default: any `ai_settings:read` holder sees only curated, ai-engineer-maintained `vendor_label`/`model_family_label` per alias (e.g. "OpenAI" / "GPT-4 class") — never the literal SDK model string, base URL, or API key.

Exception (product owner's explicit decision): a **separate, grantable RBAC permission** `ai_settings:view_provider_identity` (distinct from `ai_settings:manage`/`read`, granted via the existing `organization` RBAC system — not a hardcoded role) allows seeing the literal `provider_internal`/model id on the routing canvas only. Raw API key and base URL are never returned via any API regardless of permission. This exception is scoped exclusively to the internal `ai_settings` routing-canvas endpoint; it must never appear on any partner/employer/student-facing surface, dashboard, export, or log line. Viewing raw identity is audited (`audit_logs` action `ai_settings.provider_identity_viewed`). Already written into: `docs/API_CONTRACTS.md` (ADR-0011.1), `docs/AI_PRODUCT_SPEC.md` §5.5, `docs/SECURITY_PRIVACY.md`, `docs/BUSINESS_LOGIC.md` §17.1, `docs/ARCHITECTURE.md`.

## 3. Acceptance criteria (per docs/SYSTEM_ACCEPTANCE_BAR.md)

**Workflow Builder (A+B):** a university admin can build a real student-verification flow and a real partner-approval flow — without engineering help — producing correct outcomes (auto-approve / department queue / named-staff review / email) for real trigger events. DAG/cycle enforcement, idempotent triggers, versioning (DRAFT never mutates ACTIVE), migrations up/down. Per-node audit trail with no PII/raw-payload leakage beyond `SECURITY_PRIVACY.md` limits. Canvas responsive at 375/768/1024/1440 with loading/empty/error/permission/conflict states; dry-run visually distinct from live; failed-execution inspector shows a real recoverable next action. RBAC enforced service-layer, cross-tenant isolation tested, activation requires confirmation, every write audited.

**AI Routing Canvas (C + 2b):** canvas correctly reflects live `ai_task_model_configs`/circuit-breaker state with zero mutation path bypassing the existing `ai_settings` audit flow. Curated labels shown by default; raw identity only behind `ai_settings:view_provider_identity`, audited on view. No provider/model/token/latency/base-URL/API-key leakage to any non-permitted role or any student/partner-facing surface.

## 4. Contract/doc changes already made

- `docs/API_CONTRACTS.md` — ADR-0011.1 (new permission, new response shape, audit requirement).
- `docs/AI_PRODUCT_SPEC.md` — v2.2, §1 footnote, new §5.5.
- `docs/SECURITY_PRIVACY.md` — cross-reference to ADR-0011.1.
- `docs/BUSINESS_LOGIC.md` §17.1 — new audit action line.
- `docs/ARCHITECTURE.md` — clarified V1 `/admin/ai-settings` shape is unaffected; new routing-canvas endpoint is the only surface where ADR-0011.1 applies.

## 5. Still to do before/during implementation

- `docs/DATA_MODEL.md` — add `workflow_flows`, `workflow_executions`, `ai_routing_graphs`, `ai_routing_graph_activations` (some already sketched in ARCHITECTURE.md; needs canonical entry).
- `docs/BACKLOG.md` — new epic for the AI Routing Canvas (distinct from E23), and re-sequence E23 to reflect the pulled-forward priority decision.
- `docs/BUSINESS_LOGIC.md` §16 — extend Human Review node schema doc with `assignee_mode`.
- `docs/IMPLEMENTATION_STATUS.md` — note the explicit reprioritization (Workflow Builder + AI Routing Canvas pulled ahead of Discovery/Ads Rescue) so future sessions don't treat the old priority order as current truth.
- Confirm with `backend-developer`: `ai_settings.provider_identity_viewed` audit write is a read-only event (no before/after state) — verify this doesn't violate a NOT NULL assumption in the actual `audit_logs` migration.

## 6. Next step

Hand off to `writing-plans` skill for a concrete, phased implementation plan (Phase A backend → Phase B canvas → Phase C AI node + routing canvas), executed via `backend-developer` / `frontend-developer` / `ai-engineer` per CLAUDE.md agent routing.
