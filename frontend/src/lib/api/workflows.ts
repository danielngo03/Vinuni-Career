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
  | "webhook";

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
]);

/** Consequential/AI nodes that are always advisory + confirmation-required. */
export const ADVISORY_NODE_TYPES: ReadonlySet<WorkflowNodeType> = new Set([
  "ai_suggestion",
  "human_review",
  "request_approval",
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
