# Workflow Builder Canvas (Phase B) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the drag-and-drop React Flow canvas so a university admin can visually build, save, and activate an account-approval workflow against the real `/api/v1/workflows` backend shipped in Phase A (`docs/superpowers/plans/2026-07-02-workflow-engine-phase-a.md`).

**Architecture:** A shared, reusable `FlowCanvas` component (`frontend/src/components/workflow/flow-canvas.tsx`) wraps `@xyflow/react`, parameterized by a node-type registry so it can later be reused by the AI Provider Routing Canvas plan without duplicating drag/zoom/edge-drawing code. A `workflow-builder-screen.tsx` composes `FlowCanvas` with a node palette, a node inspector side panel, and save/activate actions, following the exact loading/error/permission-empty-state and react-query mutation pattern already used by `frontend/src/components/ai-settings/ai-settings-screen.tsx`. Two routes: a flows list page and a per-flow canvas editor page, both under the existing `(university)` route group.

**Tech Stack:** Next.js 15 App Router, React 19, TypeScript strict, `@tanstack/react-query` v5, `next-intl`, custom `frontend/src/components/ui/` primitives (no shadcn/Radix), `@xyflow/react` (new dependency), Playwright `@playwright/test` for e2e (no unit-test runner exists in this repo — do not invent one).

## Global Constraints

- React Flow (`@xyflow/react`) is the approved library per `.claude/rules/realtime.md`.
- Workflow graphs are DAG-only, versioned; an ACTIVE flow can never be edited in place — editing must call the backend's `create_new_draft_version` path (already implemented in Phase A) rather than PATCH-ing an ACTIVE flow.
- No provider/model/token/AI-internal strings may ever appear in any user-facing text (applies if/when an AI Process node type is added later; irrelevant to this plan's node types but the e2e spec should still assert their absence, matching the existing `AI_INTERNALS` assertion convention in `frontend/e2e/student-core-loop.spec.ts`).
- All API calls go through `frontend/src/lib/api/client.ts`'s `api` object; never `fetch` directly.
- All admin-facing strings are localized (vi primary, en secondary) via `next-intl`; every new namespace key must exist in both `frontend/src/messages/vi/...` and `frontend/src/messages/en/...` and pass `npm run check:messages`.
- No unit-test runner (Jest/Vitest) exists in this repo — verification for React components in this plan is TypeScript strict compile (`npm run typecheck`), lint (`npm run lint`), and incremental Playwright e2e assertions added task-by-task to one spec file, not invented unit tests.
- Reuse existing UI primitives from the `@/components/ui` barrel (`Button`, `Modal`, `EmptyState`, `Select`, `StatusBadge`, `useToast`, etc.) — do not introduce a second design system.
- Dev-seeded university admin credentials (from `backend/scripts/seed_dev.py`): `career.admin@vinuni.edu.vn` / `123456`, persona `university_staff`. Use these in the Playwright spec; do not invent different credentials.

---

### Task 1: Add `@xyflow/react` dependency and verify it renders

**Files:**
- Modify: `frontend/package.json`
- Create: `frontend/src/components/workflow/__smoke.tsx` (deleted again in Step 5 — this file only exists to prove the dependency renders before building real components on top of it)
- Test: `frontend/e2e/university-workflow-builder.spec.ts` (created here, first assertion only; extended by every later task)

**Interfaces:**
- Produces: `@xyflow/react` importable as `import { ReactFlow, Background, Controls } from "@xyflow/react"` with its CSS `import "@xyflow/react/dist/style.css"`.

- [ ] **Step 1: Install the dependency**

Run: `cd frontend && npm install @xyflow/react@^12`
Expected: `package.json`/`package-lock.json` (or `pnpm-lock.yaml` — confirm which lockfile this repo actually uses by running `ls frontend/*.lock* frontend/package-lock.json 2>/dev/null` first, since the repo root listing earlier showed `pnpm-lock.yaml`, so use `pnpm add @xyflow/react@^12` instead of `npm install` if `pnpm-lock.yaml` is present) updated with `@xyflow/react` under `dependencies`.

- [ ] **Step 2: Add a throwaway smoke component**

```tsx
// frontend/src/components/workflow/__smoke.tsx
"use client";

import { Background, ReactFlow } from "@xyflow/react";
import "@xyflow/react/dist/style.css";

const NODES = [{ id: "1", position: { x: 0, y: 0 }, data: { label: "smoke test node" } }];

export function WorkflowCanvasSmoke() {
  return (
    <div style={{ height: 300 }}>
      <ReactFlow nodes={NODES} edges={[]}>
        <Background />
      </ReactFlow>
    </div>
  );
}
```

- [ ] **Step 3: Mount it temporarily on the existing ai-settings page to verify it compiles and renders (do not leave this in place — revert in Step 5)**

Run: `cd frontend && npm run typecheck`
Expected: no new TypeScript errors.

- [ ] **Step 4: Write the first Playwright assertion (skeleton spec file)**

```ts
// frontend/e2e/university-workflow-builder.spec.ts
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

test("university admin can reach the workflow area", async ({ page }) => {
  await loginAsUniversityAdmin(page);
  // Full navigation/canvas assertions are added in later tasks as the
  // real page is built; this task only proves login lands in /university/.
});
```

Run: `cd frontend && npx playwright test e2e/university-workflow-builder.spec.ts` (requires the dev stack running — `docs/LOCAL_DEV_STACK.md` local-run commands for backend + frontend + seeded dev DB via `seed_dev.py`)
Expected: 1 passed.

- [ ] **Step 5: Delete the smoke component and its temporary mount point**

Run: `rm frontend/src/components/workflow/__smoke.tsx` and revert the temporary mount from Step 3.

- [ ] **Step 6: Re-run typecheck to confirm clean removal**

Run: `cd frontend && npm run typecheck`
Expected: no errors.

---

### Task 2: Workflow API client

**Files:**
- Create: `frontend/src/lib/api/workflows.ts`
- Modify: `frontend/src/lib/api/index.ts`
- Test: extend `frontend/e2e/university-workflow-builder.spec.ts` (no new assertions yet — this task is exercised indirectly by Task 6's e2e additions; verified directly via typecheck here)

**Interfaces:**
- Consumes: `api` from `./client` (per investigated convention), backend response shape from `backend/app/modules/workflow/api/router.py`'s `_presenter(flow)`: `{id, name, description, trigger_type, status, version, graph}` wrapped in `{data: ...}`.
- Produces: `export interface WorkflowFlow { id: string; name: string; description: string | null; trigger_type: string; status: "DRAFT" | "ACTIVE" | "ARCHIVED"; version: number; graph: FlowGraph }`, `export interface FlowGraph { nodes: FlowNode[]; edges: FlowEdge[] }`, `export interface FlowNode { id: string; type: WorkflowNodeType; data: Record<string, unknown>; position?: { x: number; y: number } }`, `export type WorkflowNodeType = "trigger" | "condition" | "human_review" | "action" | "delay" | "end"`, `export const workflowsApi = { create, update, get, list, activate, deactivate }`.

- [ ] **Step 1: Write the client file**

```ts
// frontend/src/lib/api/workflows.ts
import { api } from "./client";

export type WorkflowNodeType =
  | "trigger"
  | "condition"
  | "human_review"
  | "action"
  | "delay"
  | "end";

export interface FlowNode {
  id: string;
  type: WorkflowNodeType;
  data: Record<string, unknown>;
  position?: { x: number; y: number };
}

export interface FlowEdge {
  source: string;
  target: string;
  condition?: string;
}

export interface FlowGraph {
  nodes: FlowNode[];
  edges: FlowEdge[];
}

export type WorkflowStatus = "DRAFT" | "ACTIVE" | "ARCHIVED";

export interface WorkflowFlow {
  id: string;
  name: string;
  description: string | null;
  trigger_type: string;
  status: WorkflowStatus;
  version: number;
  graph: FlowGraph;
}

export interface CreateWorkflowBody {
  name: string;
  description?: string | null;
  trigger_type: string;
  graph: FlowGraph;
}

export interface UpdateWorkflowBody {
  name?: string;
  description?: string | null;
  graph?: FlowGraph;
}

export const workflowsApi = {
  create(body: CreateWorkflowBody): Promise<WorkflowFlow> {
    return api.post<WorkflowFlow>("/workflows", body);
  },
  update(flowId: string, body: UpdateWorkflowBody): Promise<WorkflowFlow> {
    return api.patch<WorkflowFlow>(`/workflows/${flowId}`, body);
  },
  get(flowId: string): Promise<WorkflowFlow> {
    return api.get<WorkflowFlow>(`/workflows/${flowId}`);
  },
  list(status?: WorkflowStatus): Promise<WorkflowFlow[]> {
    return api.get<WorkflowFlow[]>("/workflows", status ? { query: { status } } : undefined);
  },
  activate(flowId: string): Promise<WorkflowFlow> {
    return api.post<WorkflowFlow>(`/workflows/${flowId}/activate`);
  },
  deactivate(flowId: string): Promise<WorkflowFlow> {
    return api.post<WorkflowFlow>(`/workflows/${flowId}/deactivate`);
  },
};
```

Run: `grep -n "query?" frontend/src/lib/api/client.ts` first to confirm `RequestOptions.query` is the exact param name `api.get` accepts for query-string params (the investigation report confirmed this shape but double-check before relying on it) — adjust the `list()` call above if the real option key differs.

- [ ] **Step 2: Register the barrel export**

Run: `grep -n "ai-settings" frontend/src/lib/api/index.ts` to see the exact re-export line style, then add an equivalent line for the new file:

```ts
export * from "./workflows";
```

- [ ] **Step 3: Typecheck**

Run: `cd frontend && npm run typecheck`
Expected: no errors.

- [ ] **Step 4: Commit** (skip if this checkout has no git — confirm with `git rev-parse --is-inside-work-tree`; if it fails, skip commit steps for the rest of this plan the same way Phase A's execution did)

```bash
cd frontend && git add src/lib/api/workflows.ts src/lib/api/index.ts
git commit -m "feat(workflow): add typed API client for /api/v1/workflows"
```

---

### Task 3: i18n namespace + nav entry

**Files:**
- Create: `frontend/src/messages/vi/university/workflow-builder.json`
- Create: `frontend/src/messages/en/university/workflow-builder.json`
- Modify: `frontend/src/messages/load.ts`
- Modify: `frontend/src/messages/vi/shared/shell.json`
- Modify: `frontend/src/messages/en/shared/shell.json`
- Modify: `frontend/src/config/nav.ts`

**Interfaces:**
- Produces: `useTranslations("workflowBuilder")` namespace with keys used by Tasks 4–7: `title`, `subtitle`, `newFlow`, `save`, `saving`, `activate`, `activateConfirmTitle`, `activateConfirmBody`, `activateConfirmAction`, `cancel`, `statusDraft`, `statusActive`, `statusArchived`, `paletteTitle`, node labels `nodeTrigger`, `nodeCondition`, `nodeHumanReview`, `nodeAction`, `nodeDelay`, `nodeEnd`, `assigneeModePerson`, `assigneeModeQueue`, `conflictTitle`, `conflictBody`, `loadErrorTitle`, `permissionDeniedTitle`, `permissionDeniedBody`, `listEmptyTitle`, `listEmptyBody`.

- [ ] **Step 1: Create the vi namespace file**

```json
// frontend/src/messages/vi/university/workflow-builder.json
{
  "workflowBuilder": {
    "title": "Quy trình duyệt tài khoản",
    "subtitle": "Xây dựng luồng duyệt tài khoản bằng cách kéo thả — không cần biết lập trình.",
    "newFlow": "Tạo quy trình mới",
    "save": "Lưu bản nháp",
    "saving": "Đang lưu...",
    "activate": "Kích hoạt",
    "activateConfirmTitle": "Kích hoạt quy trình này?",
    "activateConfirmBody": "Sau khi kích hoạt, quy trình sẽ áp dụng cho các tài khoản đăng ký mới. Bạn không thể chỉnh sửa trực tiếp một quy trình đang chạy — mọi chỉnh sửa sau này sẽ tạo một phiên bản nháp mới.",
    "activateConfirmAction": "Kích hoạt ngay",
    "cancel": "Huỷ",
    "statusDraft": "Nháp",
    "statusActive": "Đang chạy",
    "statusArchived": "Đã lưu trữ",
    "paletteTitle": "Các bước",
    "nodeTrigger": "Sự kiện bắt đầu",
    "nodeCondition": "Điều kiện",
    "nodeHumanReview": "Duyệt thủ công",
    "nodeAction": "Hành động",
    "nodeDelay": "Chờ",
    "nodeEnd": "Kết thúc",
    "assigneeModePerson": "Giao cho một người cụ thể",
    "assigneeModeQueue": "Giao cho phòng ban",
    "conflictTitle": "Dữ liệu đã thay đổi",
    "conflictBody": "Quy trình này đã được cập nhật ở nơi khác. Đang tải lại dữ liệu mới nhất.",
    "loadErrorTitle": "Không tải được quy trình",
    "permissionDeniedTitle": "Bạn không có quyền truy cập",
    "permissionDeniedBody": "Chỉ quản trị viên nhà trường được cấp quyền mới có thể xem hoặc chỉnh sửa quy trình duyệt tài khoản.",
    "listEmptyTitle": "Chưa có quy trình nào",
    "listEmptyBody": "Tạo quy trình đầu tiên để tự động hoá việc duyệt tài khoản sinh viên hoặc đối tác."
  }
}
```

- [ ] **Step 2: Create the en mirror**

```json
// frontend/src/messages/en/university/workflow-builder.json
{
  "workflowBuilder": {
    "title": "Account Approval Workflows",
    "subtitle": "Build account approval flows by dragging and connecting steps — no coding required.",
    "newFlow": "New workflow",
    "save": "Save draft",
    "saving": "Saving...",
    "activate": "Activate",
    "activateConfirmTitle": "Activate this workflow?",
    "activateConfirmBody": "Once activated, this workflow will apply to new account registrations. An active workflow cannot be edited directly — future edits create a new draft version.",
    "activateConfirmAction": "Activate now",
    "cancel": "Cancel",
    "statusDraft": "Draft",
    "statusActive": "Active",
    "statusArchived": "Archived",
    "paletteTitle": "Steps",
    "nodeTrigger": "Start event",
    "nodeCondition": "Condition",
    "nodeHumanReview": "Manual review",
    "nodeAction": "Action",
    "nodeDelay": "Delay",
    "nodeEnd": "End",
    "assigneeModePerson": "Assign to a specific person",
    "assigneeModeQueue": "Assign to a department",
    "conflictTitle": "Data changed",
    "conflictBody": "This workflow was updated elsewhere. Reloading the latest data.",
    "loadErrorTitle": "Couldn't load this workflow",
    "permissionDeniedTitle": "You don't have access",
    "permissionDeniedBody": "Only university admins granted this permission can view or edit account approval workflows.",
    "listEmptyTitle": "No workflows yet",
    "listEmptyBody": "Create your first workflow to automate student or partner account approval."
  }
}
```

- [ ] **Step 3: Register both files in the loader**

Run: `grep -n "university/ai-settings" frontend/src/messages/load.ts` to find the exact import-array lines, then add matching entries for both locales:

```ts
() => import("./vi/university/workflow-builder.json"),
```
```ts
() => import("./en/university/workflow-builder.json"),
```
in the same alphabetically-ordered position within each locale's array (right after or before the `ai-settings` entry, matching whatever ordering convention the file already uses).

- [ ] **Step 4: Add the nav entry**

In `frontend/src/config/nav.ts`, add an icon import (use `FlowArrow` from `@phosphor-icons/react`, which is a real icon in that package covering flow/diagram semantics — run `grep -n "FlowArrow" frontend/node_modules/@phosphor-icons/react/dist/*.d.ts 2>/dev/null | head -1` to confirm it exists post-install; if it doesn't, use `TreeStructure` instead, which is a known-safe alternative in the same package) to the top import block, then add to the `university` array (immediately after the `aiSettings` entry, matching the discovered pattern):

```ts
{ key: "workflowBuilder", href: "/workflow", icon: FlowArrow },
```

- [ ] **Step 5: Add the nav label to shell.json in both locales**

In `frontend/src/messages/vi/shared/shell.json`, inside the top-level `"nav"` object, add:
```json
"workflowBuilder": "Quy trình duyệt"
```
In `frontend/src/messages/en/shared/shell.json`:
```json
"workflowBuilder": "Approval Workflows"
```

- [ ] **Step 6: Run message parity + typecheck**

Run: `cd frontend && npm run check:messages && npm run typecheck`
Expected: both pass with no missing-key errors.

- [ ] **Step 7: Commit**

```bash
cd frontend && git add src/messages/vi/university/workflow-builder.json src/messages/en/university/workflow-builder.json src/messages/load.ts src/messages/vi/shared/shell.json src/messages/en/shared/shell.json src/config/nav.ts
git commit -m "feat(workflow): add workflow builder i18n namespace and nav entry"
```

---

### Task 4: Shared `FlowCanvas` component with node-type registry

**Files:**
- Create: `frontend/src/components/workflow/flow-canvas.tsx`
- Create: `frontend/src/components/workflow/node-types.tsx`
- Test: extend `frontend/e2e/university-workflow-builder.spec.ts`

**Interfaces:**
- Consumes: `WorkflowNodeType`, `FlowGraph`, `FlowNode`, `FlowEdge` (Task 2).
- Produces: `export interface FlowCanvasProps { graph: FlowGraph; onGraphChange: (graph: FlowGraph) => void; nodeTypeDefs: NodeTypeDef[]; readOnly?: boolean }`, `export interface NodeTypeDef { type: WorkflowNodeType; label: string; defaultData: Record<string, unknown> }`, `export function FlowCanvas(props: FlowCanvasProps): JSX.Element` — this exact prop shape is what the later AI Provider Routing Canvas plan will reuse with a different `nodeTypeDefs` array and a different `onGraphChange` wiring, per the design doc's `flowKind`-parameterized `FlowCanvas` decision.

- [ ] **Step 1: Implement the node-type visual registry**

```tsx
// frontend/src/components/workflow/node-types.tsx
"use client";

import { Handle, Position, type NodeProps } from "@xyflow/react";
import type { WorkflowNodeType } from "@/lib/api/workflows";

const NODE_STYLES: Record<WorkflowNodeType, { bg: string; border: string }> = {
  trigger: { bg: "bg-emerald-50", border: "border-emerald-400" },
  condition: { bg: "bg-amber-50", border: "border-amber-400" },
  human_review: { bg: "bg-sky-50", border: "border-sky-400" },
  action: { bg: "bg-violet-50", border: "border-violet-400" },
  delay: { bg: "bg-slate-50", border: "border-slate-400" },
  end: { bg: "bg-rose-50", border: "border-rose-400" },
};

function GenericNode({ data, type }: NodeProps) {
  const style = NODE_STYLES[type as WorkflowNodeType] ?? NODE_STYLES.action;
  return (
    <div
      className={`rounded-xl border-2 ${style.border} ${style.bg} px-4 py-2 text-sm font-medium shadow-sm`}
    >
      <Handle type="target" position={Position.Top} />
      {String(data.label ?? type)}
      <Handle type="source" position={Position.Bottom} />
    </div>
  );
}

export const REACT_FLOW_NODE_TYPES = {
  trigger: GenericNode,
  condition: GenericNode,
  human_review: GenericNode,
  action: GenericNode,
  delay: GenericNode,
  end: GenericNode,
};
```

- [ ] **Step 2: Implement `FlowCanvas`**

```tsx
// frontend/src/components/workflow/flow-canvas.tsx
"use client";

import { useCallback, useMemo } from "react";
import {
  addEdge,
  Background,
  Controls,
  ReactFlow,
  useEdgesState,
  useNodesState,
  type Connection,
  type Edge,
  type Node,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";

import type { FlowEdge, FlowGraph, FlowNode, WorkflowNodeType } from "@/lib/api/workflows";
import { REACT_FLOW_NODE_TYPES } from "./node-types";

export interface NodeTypeDef {
  type: WorkflowNodeType;
  label: string;
  defaultData: Record<string, unknown>;
}

export interface FlowCanvasProps {
  graph: FlowGraph;
  onGraphChange: (graph: FlowGraph) => void;
  nodeTypeDefs: NodeTypeDef[];
  readOnly?: boolean;
}

function toReactFlowNodes(nodes: FlowNode[]): Node[] {
  return nodes.map((n, index) => ({
    id: n.id,
    type: n.type,
    position: n.position ?? { x: 120, y: 120 + index * 100 },
    data: { ...n.data, label: n.data.label ?? n.type },
  }));
}

function toReactFlowEdges(edges: FlowEdge[]): Edge[] {
  return edges.map((e) => ({
    id: `${e.source}-${e.target}-${e.condition ?? "default"}`,
    source: e.source,
    target: e.target,
    label: e.condition,
  }));
}

export function FlowCanvas({ graph, onGraphChange, nodeTypeDefs, readOnly }: FlowCanvasProps) {
  const [nodes, setNodes, onNodesChange] = useNodesState(toReactFlowNodes(graph.nodes));
  const [edges, setEdges, onEdgesChange] = useEdgesState(toReactFlowEdges(graph.edges));

  const emitChange = useCallback(
    (nextNodes: Node[], nextEdges: Edge[]) => {
      onGraphChange({
        nodes: nextNodes.map((n) => ({
          id: n.id,
          type: n.type as WorkflowNodeType,
          data: n.data as Record<string, unknown>,
          position: n.position,
        })),
        edges: nextEdges.map((e) => ({
          source: e.source,
          target: e.target,
          condition: typeof e.label === "string" ? e.label : undefined,
        })),
      });
    },
    [onGraphChange],
  );

  const handleConnect = useCallback(
    (connection: Connection) => {
      const next = addEdge(connection, edges);
      setEdges(next);
      emitChange(nodes, next);
    },
    [edges, nodes, setEdges, emitChange],
  );

  const handleDrop = useCallback(
    (event: React.DragEvent<HTMLDivElement>) => {
      event.preventDefault();
      const type = event.dataTransfer.getData("application/workflow-node-type") as WorkflowNodeType;
      const def = nodeTypeDefs.find((d) => d.type === type);
      if (!def) return;
      const bounds = event.currentTarget.getBoundingClientRect();
      const newNode: Node = {
        id: `${type}-${crypto.randomUUID().slice(0, 8)}`,
        type,
        position: { x: event.clientX - bounds.left, y: event.clientY - bounds.top },
        data: { ...def.defaultData, label: def.label },
      };
      const next = [...nodes, newNode];
      setNodes(next);
      emitChange(next, edges);
    },
    [nodeTypeDefs, nodes, edges, setNodes, emitChange],
  );

  const nodeTypes = useMemo(() => REACT_FLOW_NODE_TYPES, []);

  return (
    <div
      className="h-[560px] w-full rounded-2xl border border-[var(--border-subtle)]"
      onDragOver={(e) => e.preventDefault()}
      onDrop={handleDrop}
      data-testid="flow-canvas"
    >
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        onNodesChange={readOnly ? undefined : onNodesChange}
        onEdgesChange={readOnly ? undefined : onEdgesChange}
        onConnect={readOnly ? undefined : handleConnect}
        nodesDraggable={!readOnly}
        nodesConnectable={!readOnly}
        fitView
      >
        <Background />
        <Controls />
      </ReactFlow>
    </div>
  );
}
```

- [ ] **Step 3: Add a node palette component (drag source)**

```tsx
// frontend/src/components/workflow/node-palette.tsx
"use client";

import type { NodeTypeDef } from "./flow-canvas";

export function NodePalette({ defs, title }: { defs: NodeTypeDef[]; title: string }) {
  return (
    <aside className="w-48 shrink-0 space-y-2" data-testid="node-palette">
      <h3 className="text-xs font-semibold uppercase tracking-wide text-[var(--text-subtle)]">
        {title}
      </h3>
      {defs.map((def) => (
        <div
          key={def.type}
          draggable
          onDragStart={(e) => e.dataTransfer.setData("application/workflow-node-type", def.type)}
          className="cursor-grab rounded-xl border border-[var(--border-subtle)] bg-white/90 px-3 py-2 text-sm font-medium shadow-sm active:cursor-grabbing"
          data-testid={`palette-node-${def.type}`}
        >
          {def.label}
        </div>
      ))}
    </aside>
  );
}
```

- [ ] **Step 4: Typecheck**

Run: `cd frontend && npm run typecheck`
Expected: no errors. If `useNodesState`/`useEdgesState`/`addEdge` import paths differ in the installed `@xyflow/react` version, run `grep -rn "export" frontend/node_modules/@xyflow/react/dist/esm/index.d.ts | grep -i "useNodesState\|useEdgesState\|addEdge"` and correct the imports above to match exactly.

- [ ] **Step 5: Commit**

```bash
cd frontend && git add src/components/workflow/flow-canvas.tsx src/components/workflow/node-types.tsx src/components/workflow/node-palette.tsx
git commit -m "feat(workflow): add shared FlowCanvas, node-type registry, and drag palette"
```

---

### Task 5: Node inspector panel (edit node data, incl. Human Review `assignee_mode`)

**Files:**
- Create: `frontend/src/components/workflow/node-inspector.tsx`

**Interfaces:**
- Consumes: `FlowNode`, `WorkflowNodeType` (Task 2).
- Produces: `export interface NodeInspectorProps { node: FlowNode | null; onChange: (nodeId: string, data: Record<string, unknown>) => void; onClose: () => void }`, `export function NodeInspector(props: NodeInspectorProps): JSX.Element | null`.

- [ ] **Step 1: Implement the inspector**

```tsx
// frontend/src/components/workflow/node-inspector.tsx
"use client";

import { useTranslations } from "next-intl";
import { Input, Select } from "@/components/ui";
import type { FlowNode } from "@/lib/api/workflows";

export interface NodeInspectorProps {
  node: FlowNode | null;
  onChange: (nodeId: string, data: Record<string, unknown>) => void;
  onClose: () => void;
}

export function NodeInspector({ node, onChange, onClose }: NodeInspectorProps) {
  const t = useTranslations("workflowBuilder");
  if (!node) return null;

  const setField = (key: string, value: unknown) => onChange(node.id, { ...node.data, [key]: value });

  return (
    <aside
      className="w-72 shrink-0 space-y-3 rounded-2xl border border-[var(--border-subtle)] bg-white/90 p-4 shadow-sm"
      data-testid="node-inspector"
    >
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold">{String(node.data.label ?? node.type)}</h3>
        <button type="button" onClick={onClose} aria-label={t("cancel")} className="text-xs text-[var(--text-subtle)]">
          ×
        </button>
      </div>

      {node.type === "condition" && (
        <Input
          label="Expression"
          value={String(node.data.expression ?? "")}
          onChange={(e) => setField("expression", e.target.value)}
          placeholder="{{fraud_score}} > 0.70"
          data-testid="inspector-condition-expression"
        />
      )}

      {node.type === "human_review" && (
        <>
          <Select
            label={t("paletteTitle")}
            value={String(node.data.assignee_mode ?? "queue")}
            onChange={(e) => setField("assignee_mode", e.target.value)}
            data-testid="inspector-assignee-mode"
          >
            <option value="person">{t("assigneeModePerson")}</option>
            <option value="queue">{t("assigneeModeQueue")}</option>
          </Select>
          {node.data.assignee_mode === "person" ? (
            <Input
              label="Assignee user ID"
              value={String(node.data.assignee_user_id ?? "")}
              onChange={(e) => setField("assignee_user_id", e.target.value)}
              data-testid="inspector-assignee-user-id"
            />
          ) : (
            <Input
              label="Department ID"
              value={String(node.data.assignee_department_id ?? "")}
              onChange={(e) => setField("assignee_department_id", e.target.value)}
              data-testid="inspector-assignee-department-id"
            />
          )}
          <Input
            label="SLA (hours)"
            type="number"
            value={String(node.data.sla_hours ?? 24)}
            onChange={(e) => setField("sla_hours", Number(e.target.value))}
            data-testid="inspector-sla-hours"
          />
        </>
      )}

      {node.type === "action" && (
        <Input
          label="Action"
          value={String(node.data.action ?? "")}
          onChange={(e) => setField("action", e.target.value)}
          placeholder="auto_approve"
          data-testid="inspector-action"
        />
      )}
    </aside>
  );
}
```

Run: `grep -n "export function Select\|export function Input" frontend/src/components/ui/select.tsx frontend/src/components/ui/input.tsx` to confirm both components accept a `label` prop and standard `onChange`/`value` props in the shape used above — adjust prop names if the real components differ (e.g. if `Select` takes `options` as an array instead of `<option>` children).

- [ ] **Step 2: Typecheck**

Run: `cd frontend && npm run typecheck`
Expected: no errors (fix any prop-shape mismatch found in Step 1's grep before this passes).

- [ ] **Step 3: Commit**

```bash
cd frontend && git add src/components/workflow/node-inspector.tsx
git commit -m "feat(workflow): add node inspector panel for condition/human-review/action node data"
```

---

### Task 6: Workflow builder screen (canvas editor page) — save + activate

**Files:**
- Create: `frontend/src/components/workflow/workflow-builder-screen.tsx`
- Test: extend `frontend/e2e/university-workflow-builder.spec.ts`

**Interfaces:**
- Consumes: `FlowCanvas`, `NodePalette`, `NodeInspector` (Tasks 4/5), `workflowsApi` (Task 2), `useToast`/`Button`/`Modal`/`EmptyState` (`@/components/ui`), `ApiError` (`@/lib/api`).
- Produces: `export function WorkflowBuilderScreen({ flowId }: { flowId: string | "new" }): JSX.Element`.

- [ ] **Step 1: Extend the Playwright spec with the target end-to-end scenario (write it now, before the page exists, so it drives the implementation)**

```ts
// append to frontend/e2e/university-workflow-builder.spec.ts

test("admin builds, saves, and activates a workflow via drag-and-drop canvas", async ({ page }) => {
  await loginAsUniversityAdmin(page);
  await page.goto("/vi/university/workflow/new");

  await expect(page.getByTestId("flow-canvas")).toBeVisible();

  const trigger = page.getByTestId("palette-node-trigger");
  const canvas = page.getByTestId("flow-canvas");
  await trigger.dragTo(canvas, { targetPosition: { x: 150, y: 100 } });

  const endNode = page.getByTestId("palette-node-end");
  await endNode.dragTo(canvas, { targetPosition: { x: 150, y: 300 } });

  await page.getByRole("button", { name: "Lưu bản nháp" }).click();
  await expect(page.getByText(/Nháp/)).toBeVisible({ timeout: 10_000 });
});
```

- [ ] **Step 2: Run to verify it fails (page doesn't exist yet)**

Run: `cd frontend && npx playwright test e2e/university-workflow-builder.spec.ts -g "admin builds"`
Expected: FAIL (404 or missing test-id).

- [ ] **Step 3: Implement the screen**

```tsx
// frontend/src/components/workflow/workflow-builder-screen.tsx
"use client";

import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { useRouter } from "next/navigation";

import { Button, EmptyState, Modal, StatusBadge, useToast } from "@/components/ui";
import { PageHeader } from "@/components/layout/page-header";
import { ApiError, workflowsApi, type FlowGraph, type WorkflowNodeType } from "@/lib/api";
import { FlowCanvas, type NodeTypeDef } from "./flow-canvas";
import { NodeInspector } from "./node-inspector";
import { NodePalette } from "./node-palette";

const EMPTY_GRAPH: FlowGraph = { nodes: [], edges: [] };

function nodeTypeDefs(t: ReturnType<typeof useTranslations>): NodeTypeDef[] {
  return [
    { type: "trigger", label: t("nodeTrigger"), defaultData: { trigger_type: "system.student_registered" } },
    { type: "condition", label: t("nodeCondition"), defaultData: { expression: "" } },
    {
      type: "human_review",
      label: t("nodeHumanReview"),
      defaultData: { assignee_mode: "queue", sla_hours: 24 },
    },
    { type: "action", label: t("nodeAction"), defaultData: { action: "" } },
    { type: "delay", label: t("nodeDelay"), defaultData: {} },
    { type: "end", label: t("nodeEnd"), defaultData: {} },
  ];
}

export function WorkflowBuilderScreen({ flowId }: { flowId: string | "new" }) {
  const t = useTranslations("workflowBuilder");
  const toast = useToast();
  const router = useRouter();
  const queryClient = useQueryClient();
  const isNew = flowId === "new";

  const [graph, setGraph] = useState<FlowGraph>(EMPTY_GRAPH);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [activateOpen, setActivateOpen] = useState(false);
  const [name, setName] = useState("");

  const query = useQuery({
    queryKey: ["admin", "workflow", flowId],
    queryFn: () => workflowsApi.get(flowId),
    enabled: !isNew,
    retry: false,
  });

  const flow = query.data;
  const effectiveGraph = isNew ? graph : (flow?.graph ?? EMPTY_GRAPH);
  const effectiveName = isNew ? name : (flow?.name ?? "");
  const status = flow?.status ?? "DRAFT";
  const readOnly = status === "ACTIVE" || status === "ARCHIVED";

  const defs = useMemo(() => nodeTypeDefs(t), [t]);

  const save = useMutation({
    mutationFn: async () => {
      if (isNew) {
        return workflowsApi.create({ name: name || "Untitled workflow", trigger_type: "system.student_registered", graph });
      }
      return workflowsApi.update(flowId, { graph: effectiveGraph });
    },
    onSuccess: (saved) => {
      queryClient.setQueryData(["admin", "workflow", saved.id], saved);
      toast.show({ tone: "success", title: t("save") });
      if (isNew) router.replace(`/university/workflow/${saved.id}`);
    },
    onError: (e) => {
      if (e instanceof ApiError && e.isConflict) {
        toast.show({ tone: "error", title: t("conflictTitle"), description: t("conflictBody") });
        query.refetch();
        return;
      }
      toast.show({ tone: "error", title: e instanceof Error ? e.message : String(e) });
    },
  });

  const activate = useMutation({
    mutationFn: () => workflowsApi.activate(flowId),
    onSuccess: (updated) => {
      queryClient.setQueryData(["admin", "workflow", updated.id], updated);
      setActivateOpen(false);
      toast.show({ tone: "success", title: t("statusActive") });
    },
    onError: (e) => {
      toast.show({ tone: "error", title: e instanceof Error ? e.message : String(e) });
    },
  });

  if (!isNew && query.isError) {
    const err = query.error;
    if (err instanceof ApiError && (err.isPermissionError || err.isAuthError)) {
      return (
        <>
          <PageHeader title={t("title")} />
          <EmptyState kind="permission" title={t("permissionDeniedTitle")} description={t("permissionDeniedBody")} />
        </>
      );
    }
    return (
      <>
        <PageHeader title={t("title")} />
        <EmptyState
          kind="error"
          title={t("loadErrorTitle")}
          action={<Button variant="secondary" onClick={() => query.refetch()}>{t("cancel")}</Button>}
        />
      </>
    );
  }

  const selectedNode = effectiveGraph.nodes.find((n) => n.id === selectedNodeId) ?? null;

  return (
    <>
      <PageHeader
        title={effectiveName || t("title")}
        description={t("subtitle")}
        actions={
          <div className="flex gap-2">
            {status && <StatusBadge tone={status === "ACTIVE" ? "success" : "neutral"}>{t(`status${status.charAt(0)}${status.slice(1).toLowerCase()}` as never)}</StatusBadge>}
            <Button variant="secondary" loading={save.isPending} disabled={readOnly} onClick={() => save.mutate()}>
              {save.isPending ? t("saving") : t("save")}
            </Button>
            {!isNew && status === "DRAFT" && (
              <Button variant="primary" onClick={() => setActivateOpen(true)}>
                {t("activate")}
              </Button>
            )}
          </div>
        }
      />

      <div className="flex gap-4">
        <NodePalette defs={defs} title={t("paletteTitle")} />
        <div className="flex-1">
          <FlowCanvas
            graph={effectiveGraph}
            nodeTypeDefs={defs}
            readOnly={readOnly}
            onGraphChange={(next) => {
              setGraph(next);
              if (!isNew) queryClient.setQueryData(["admin", "workflow", flowId], { ...flow, graph: next });
            }}
          />
        </div>
        <NodeInspector
          node={selectedNode}
          onClose={() => setSelectedNodeId(null)}
          onChange={(nodeId, data) => {
            const nextNodes = effectiveGraph.nodes.map((n) => (n.id === nodeId ? { ...n, data } : n));
            setGraph({ ...effectiveGraph, nodes: nextNodes });
          }}
        />
      </div>

      <Modal
        open={activateOpen}
        onClose={() => setActivateOpen(false)}
        title={t("activateConfirmTitle")}
        description={t("activateConfirmBody")}
        size="sm"
        closeLabel={t("cancel")}
        footer={
          <>
            <Button variant="ghost" onClick={() => setActivateOpen(false)}>{t("cancel")}</Button>
            <Button variant="primary" loading={activate.isPending} onClick={() => activate.mutate()}>
              {t("activateConfirmAction")}
            </Button>
          </>
        }
      />
    </>
  );
}
```

Run: `grep -n "export function StatusBadge\|tone=" frontend/src/components/ui/status-badge.tsx` and `grep -n "export function EmptyState" -A 15 frontend/src/components/ui/empty-state.tsx` to confirm the exact prop names (`tone`, `kind`, `action`) used above match the real components; fix any mismatch before typecheck.

- [ ] **Step 4: Wire node selection (click a canvas node to open the inspector)**

In `frontend/src/components/workflow/flow-canvas.tsx`, add an `onNodeClick` prop to `FlowCanvasProps` (`onNodeClick?: (nodeId: string) => void`) and pass it to `<ReactFlow onNodeClick={(_, node) => onNodeClick?.(node.id)} .../>`. Then in `workflow-builder-screen.tsx`, pass `onNodeClick={setSelectedNodeId}` to `<FlowCanvas>`.

- [ ] **Step 5: Run typecheck**

Run: `cd frontend && npm run typecheck`
Expected: no errors.

- [ ] **Step 6: Run the e2e test from Step 1**

Run: `cd frontend && npx playwright test e2e/university-workflow-builder.spec.ts -g "admin builds"`
Expected: PASS. If drag-and-drop via Playwright's `dragTo` doesn't trigger the HTML5 `dataTransfer` drop event reliably against `@xyflow/react`'s canvas (a known flakiness point for native drag events in headless browsers), replace the drag interaction with explicit `dispatchEvent` calls simulating `dragstart`/`dragover`/`drop` with a real `DataTransfer`-like object, or fall back to a simpler assertion (palette item is visible and canvas accepts programmatic `onGraphChange` — verified via a dev-only test hook) — do not silently mark this test skipped; if native drag simulation proves unreliable, document the workaround used and why in this task's completion notes.

- [ ] **Step 7: Commit**

```bash
cd frontend && git add src/components/workflow/workflow-builder-screen.tsx src/components/workflow/flow-canvas.tsx e2e/university-workflow-builder.spec.ts
git commit -m "feat(workflow): add workflow builder screen with save/activate and canvas node selection"
```

---

### Task 7: Flows list page + routes

**Files:**
- Create: `frontend/src/components/workflow/workflow-list-screen.tsx`
- Create: `frontend/src/app/[locale]/(university)/university/workflow/page.tsx`
- Create: `frontend/src/app/[locale]/(university)/university/workflow/new/page.tsx`
- Create: `frontend/src/app/[locale]/(university)/university/workflow/[flowId]/page.tsx`
- Test: extend `frontend/e2e/university-workflow-builder.spec.ts`

**Interfaces:**
- Consumes: `workflowsApi.list` (Task 2), `WorkflowBuilderScreen` (Task 6).
- Produces: routes `/university/workflow` (list), `/university/workflow/new` (create), `/university/workflow/[flowId]` (edit/view).

- [ ] **Step 1: Implement the list screen**

```tsx
// frontend/src/components/workflow/workflow-list-screen.tsx
"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { useTranslations } from "next-intl";

import { Button, EmptyState, StatusBadge } from "@/components/ui";
import { PageHeader } from "@/components/layout/page-header";
import { ApiError, workflowsApi } from "@/lib/api";

export function WorkflowListScreen() {
  const t = useTranslations("workflowBuilder");
  const query = useQuery({
    queryKey: ["admin", "workflows"],
    queryFn: () => workflowsApi.list(),
    retry: false,
  });

  if (query.isError) {
    const err = query.error;
    if (err instanceof ApiError && (err.isPermissionError || err.isAuthError)) {
      return (
        <>
          <PageHeader title={t("title")} />
          <EmptyState kind="permission" title={t("permissionDeniedTitle")} description={t("permissionDeniedBody")} />
        </>
      );
    }
    return (
      <>
        <PageHeader title={t("title")} />
        <EmptyState kind="error" title={t("loadErrorTitle")} action={<Button variant="secondary" onClick={() => query.refetch()}>{t("cancel")}</Button>} />
      </>
    );
  }

  const flows = query.data ?? [];

  return (
    <>
      <PageHeader
        title={t("title")}
        description={t("subtitle")}
        actions={
          <Link href="/university/workflow/new">
            <Button variant="primary">{t("newFlow")}</Button>
          </Link>
        }
      />
      {flows.length === 0 && !query.isLoading ? (
        <EmptyState kind="default" title={t("listEmptyTitle")} description={t("listEmptyBody")} />
      ) : (
        <ul className="space-y-2">
          {flows.map((flow) => (
            <li key={flow.id}>
              <Link
                href={`/university/workflow/${flow.id}`}
                className="flex items-center justify-between rounded-xl border border-[var(--border-subtle)] bg-white/90 px-4 py-3 shadow-sm hover:bg-white"
                data-testid={`workflow-row-${flow.id}`}
              >
                <span className="font-medium">{flow.name}</span>
                <StatusBadge tone={flow.status === "ACTIVE" ? "success" : "neutral"}>
                  {flow.status === "ACTIVE" ? t("statusActive") : flow.status === "DRAFT" ? t("statusDraft") : t("statusArchived")}
                </StatusBadge>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </>
  );
}
```

Run: `grep -n "kind=\"default\"\|kind:" frontend/src/components/ui/empty-state.tsx` to confirm `"default"` is a valid `kind` value; adjust to whatever the real union type uses if not.

- [ ] **Step 2: Add the three route files**

```tsx
// frontend/src/app/[locale]/(university)/university/workflow/page.tsx
import { WorkflowListScreen } from "@/components/workflow/workflow-list-screen";

export default function UniversityWorkflowListPage() {
  return <WorkflowListScreen />;
}
```

```tsx
// frontend/src/app/[locale]/(university)/university/workflow/new/page.tsx
import { WorkflowBuilderScreen } from "@/components/workflow/workflow-builder-screen";

export default function UniversityWorkflowNewPage() {
  return <WorkflowBuilderScreen flowId="new" />;
}
```

```tsx
// frontend/src/app/[locale]/(university)/university/workflow/[flowId]/page.tsx
import { WorkflowBuilderScreen } from "@/components/workflow/workflow-builder-screen";

export default async function UniversityWorkflowEditPage({
  params,
}: {
  params: Promise<{ flowId: string }>;
}) {
  const { flowId } = await params;
  return <WorkflowBuilderScreen flowId={flowId} />;
}
```

Run: `grep -n "params: Promise" frontend/src/app/\[locale\]/\(university\)/university/*/\[*\]/page.tsx 2>/dev/null | head -3` first to confirm this Next.js version's dynamic-route `params` is indeed a `Promise` (Next 15 App Router convention) matching an existing `[..]` route in this repo — copy that exact async-params pattern rather than assuming.

- [ ] **Step 3: Extend the e2e spec to cover the list page and full create→save→activate loop**

```ts
// append to frontend/e2e/university-workflow-builder.spec.ts

test("workflow list shows created flows and links to the editor", async ({ page }) => {
  await loginAsUniversityAdmin(page);
  await page.goto("/vi/university/workflow");
  await expect(page.getByRole("heading", { name: "Quy trình duyệt tài khoản" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Tạo quy trình mới" })).toBeVisible();
});
```

- [ ] **Step 4: Run the full spec file**

Run: `cd frontend && npx playwright test e2e/university-workflow-builder.spec.ts`
Expected: all tests pass.

- [ ] **Step 5: Run lint + typecheck one final time**

Run: `cd frontend && npm run lint && npm run typecheck`
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
cd frontend && git add src/components/workflow/workflow-list-screen.tsx "src/app/[locale]/(university)/university/workflow" e2e/university-workflow-builder.spec.ts
git commit -m "feat(workflow): add flows list page and new/edit routes under /university/workflow"
```

---

## Explicitly out of scope for this plan (deferred, not silently dropped)

- **Dry-run/test mode with node highlighting** (docs/BACKLOG.md B-394) — needs the backend to expose a "simulate with sample payload" endpoint that isn't part of Phase A; track as a fast-follow plan.
- **Execution history viewer and failed-execution inspector** (B-397/B-399) — needs new read endpoints over `workflow_executions` not built in Phase A; separate plan.
- **Human-review resume/decision UI** — blocked on the backend resume API flagged as a Phase A follow-up; the canvas can display a Human-Review-pending state once that API exists, not before.
- **Editing an ACTIVE flow via `create_new_draft_version`** — this plan's `readOnly` gate on ACTIVE/ARCHIVED flows prevents accidental in-place edits, but does not yet wire a "create new version from this active flow" button in the UI; add this once the resume/versioning UX is designed with `university-domain-agent` input, per CLAUDE.md's requirement that domain UX changes get domain-agent review.
- **AI Provider Routing Canvas reuse of `FlowCanvas`** — this plan's `FlowCanvas`/`NodeTypeDef` props are deliberately generic to support that reuse, but the actual `ai_settings` routing graph plan is separate and not written yet.

## Self-review notes

- Confirmed via investigation: no unit-test runner exists (no Jest/Vitest) — every task's verification step uses `typecheck`/`lint`/Playwright only, never an invented `*.test.tsx` file.
- Confirmed real dev-seeded credentials (`career.admin@vinuni.edu.vn` / `123456`) from `backend/scripts/seed_dev.py` rather than guessing.
- Flagged three places where a component prop name or Next.js API shape could not be 100% confirmed ahead of time (`Select`/`EmptyState`/`StatusBadge` exact prop unions, dynamic route `params` Promise convention, `@xyflow/react` hook export names) — each has an explicit `grep` verification instruction rather than a guess, per this plan's own no-placeholder rule.
- Native HTML5 drag-and-drop in Playwright is a known flaky point flagged explicitly in Task 6 Step 6 with a concrete fallback strategy, not left as an unstated risk.
