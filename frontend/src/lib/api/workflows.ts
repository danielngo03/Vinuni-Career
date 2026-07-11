import { api } from "./client";

/**
 * Explicit node-type catalog mirrored from
 * backend/app/modules/workflow/domain/graph.py `NodeType`. `human_review`,
 * `action`, `ai_process` are legacy/generic types kept for saved graphs;
 * the spec-named types below are what the palette offers going forward
 * (docs/PARTNER_RBAC_ANALYTICS_SPEC.md "Visual Recruiting Workflow Builder
 * Contract").
 */
export type WorkflowNodeType =
  | "trigger"
  | "condition"
  | "human_review"
  | "action"
  | "delay"
  | "end"
  | "wait"
  | "assign_owner"
  | "send_notification"
  | "create_task"
  | "move_candidate"
  | "request_approval"
  | "ai_suggestion"
  | "webhook"
  // Recruiting-automation node types (Wave 2B). Mirrored from
  // backend/app/modules/workflow/domain/graph.py `NodeType`.
  | "ai_screen_application"
  | "auto_advance_on_gate"
  | "notify"
  | "jd_pdf_to_draft";

/** Node types whose real (non-simulated) execution can perform a side effect. */
export const SIDE_EFFECTING_NODE_TYPES: ReadonlySet<WorkflowNodeType> = new Set([
  "action",
  "assign_owner",
  "send_notification",
  "create_task",
  "move_candidate",
  "request_approval",
  "human_review",
  "ai_suggestion",
  "webhook",
  "ai_screen_application",
  "auto_advance_on_gate",
  "notify",
  "jd_pdf_to_draft",
]);

/** AI/advisory nodes that always pause for a human to confirm before acting. */
export const ADVISORY_NODE_TYPES: ReadonlySet<WorkflowNodeType> = new Set([
  "ai_suggestion",
  "human_review",
  "request_approval",
]);

/**
 * Consequential write/AI nodes that run AUTONOMOUSLY once the flow is activated
 * (never before). The builder marks them so an author understands they are not
 * advisory: activation is RBAC-gated and each performs a real read/meter/write.
 * `ai_screen_application` also spends AI credits when its `mode` is `llm`.
 */
export const CONSEQUENTIAL_NODE_TYPES: ReadonlySet<WorkflowNodeType> = new Set([
  "ai_screen_application",
  "auto_advance_on_gate",
  "notify",
]);

/**
 * Nodes that always PAUSE for explicit human confirm-create and never publish on
 * their own — surfaced distinctly from AI-advisory. `jd_pdf_to_draft` prepares a
 * job DRAFT proposal (`awaiting_human_review`) that a person confirms via the
 * existing job-draft flow.
 */
export const HUMAN_CONFIRM_NODE_TYPES: ReadonlySet<WorkflowNodeType> = new Set([
  "jd_pdf_to_draft",
]);

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

export type WorkflowStatus = "DRAFT" | "ACTIVE" | "PAUSED" | "ARCHIVED";

export type WorkflowOwnerType = "partner" | "university";

export interface WorkflowFlow {
  id: string;
  name: string;
  description: string | null;
  trigger_type: string;
  status: WorkflowStatus;
  version: number;
  graph: FlowGraph;
  owner_type: WorkflowOwnerType | null;
  owner_org_id: string | null;
  cloned_from_id: string | null;
  activated_at: string | null;
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

export interface DryRunStep {
  node_id: string;
  node_type: WorkflowNodeType | string;
  status: "success" | "failed" | "skipped";
  decision: string;
  /** Redacted output summary — never raw PII, tokens, or prompts. */
  output_summary: Record<string, unknown>;
  user_safe_error: string | null;
}

export interface DryRunResult {
  execution_id: string;
  is_simulated: true;
  sample_event: Record<string, unknown>;
  steps: DryRunStep[];
}

export type FailedNodeTaskStatus = "open" | "resolved" | "dismissed";

export interface FailedNodeTask {
  id: string;
  execution_id: string;
  flow_id: string;
  node_id: string;
  node_type: string;
  owner_type: WorkflowOwnerType | null;
  user_safe_error: string;
  status: FailedNodeTaskStatus;
  created_at: string;
  resolved_at: string | null;
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
  /** Suspend an ACTIVE flow. Resumable via `activate`. */
  pause(flowId: string): Promise<WorkflowFlow> {
    return api.post<WorkflowFlow>(`/workflows/${flowId}/pause`);
  },
  /** Terminal retirement. A new draft (`clone`) is required to run again. */
  archive(flowId: string): Promise<WorkflowFlow> {
    return api.post<WorkflowFlow>(`/workflows/${flowId}/archive`);
  },
  /** Duplicate any flow (including drafts) as a new draft. */
  clone(flowId: string): Promise<WorkflowFlow> {
    return api.post<WorkflowFlow>(`/workflows/${flowId}/clone`);
  },
  /** Dry-run: executes the flow against a synthetic, PII-redacted event with no real side effects. */
  test(flowId: string, sampleEvent?: Record<string, unknown>): Promise<DryRunResult> {
    return api.post<DryRunResult>(`/workflows/${flowId}/test`, {
      sample_event: sampleEvent,
    });
  },
  listTasks(status: FailedNodeTaskStatus = "open"): Promise<FailedNodeTask[]> {
    return api.get<FailedNodeTask[]>("/workflows/tasks", { query: { status } });
  },
  resolveTask(taskId: string, resolution: "resolved" | "dismissed"): Promise<FailedNodeTask> {
    return api.post<FailedNodeTask>(`/workflows/tasks/${taskId}/resolve`, { resolution });
  },
};
