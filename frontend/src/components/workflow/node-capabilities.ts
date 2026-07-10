import type { FlowGraph, FlowNode, WorkflowNodeType } from "@/lib/api/workflows";

/**
 * Default `resource:action` capability required to activate a flow containing
 * a node of this type — mirrored from
 * backend/app/modules/workflow/domain/graph.py `DEFAULT_NODE_CAPABILITY`.
 * Keep in sync with the backend map; the backend remains the source of truth
 * (this is a UI pre-check convenience, not the enforcement point).
 */
const DEFAULT_NODE_CAPABILITY: Partial<Record<WorkflowNodeType, string>> = {
  assign_owner: "jobs:assign_owner",
  send_notification: "notifications:send",
  create_task: "workflow:create_task",
  move_candidate: "pipeline:move_candidate",
  request_approval: "workflow:request_approval",
  human_review: "workflow:request_approval",
  ai_suggestion: "ai_assistant:suggest",
  webhook: "workflow:webhook",
  // Recruiting-automation nodes: activation requires the SAME capability the
  // equivalent manual action needs (backend `DEFAULT_NODE_CAPABILITY`).
  ai_screen_application: "ai_recruiting:screen_candidate",
  auto_advance_on_gate: "pipeline:move_candidate",
  notify: "notifications:send",
  jd_pdf_to_draft: "jobs:create",
};

/** Resolves the capability a node requires, honoring an explicit `data.capability` override. */
export function requiredCapabilityForNode(node: FlowNode): string | null {
  const override = node.data?.capability;
  if (typeof override === "string" && override.includes(":")) return override;
  return DEFAULT_NODE_CAPABILITY[node.type] ?? null;
}

/**
 * Best-effort client-side pre-check of every capability a graph's nodes would
 * require to activate, so the builder can warn the author before they ever
 * call `/activate` (docs/PARTNER_RBAC_ANALYTICS_SPEC.md: "Show permission
 * blockers before activation, not after a flow fails in production"). The
 * backend remains authoritative — a real activation attempt re-checks and can
 * still block with the definitive list.
 */
export function missingCapabilitiesForGraph(
  graph: FlowGraph,
  granted: ReadonlySet<string>,
  isSuperadmin: boolean,
): string[] {
  if (isSuperadmin || granted.has("*:*")) return [];
  const missing = new Set<string>();
  for (const node of graph.nodes) {
    const capability = requiredCapabilityForNode(node);
    if (!capability) continue;
    const [resource] = capability.split(":");
    if (granted.has(capability) || granted.has(`${resource}:*`)) continue;
    missing.add(capability);
  }
  return [...missing];
}
