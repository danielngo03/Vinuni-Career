import { api } from "./client";

/**
 * A routing graph is an AUTHORING artifact for one task family's fallback
 * CHAIN: an ordered list of provider nodes connected by "fallback" edges
 * (p1 -> p2 -> p3 means "try p1 first, then p2, then p3"). Activating it
 * compiles it into the real `ai_model_aliases` row the gateway reads — the
 * graph itself is never a second runtime read path (see
 * docs/superpowers/plans/2026-07-02-ai-routing-canvas.md).
 */
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

/**
 * Live provider/alias/circuit-breaker view for the routing canvas. Curated
 * `vendor_label`/`model_family_label` are the DEFAULT display; `provider_internal`
 * and `model_id` are populated ONLY when the caller holds
 * `ai_settings:view_provider_identity` — otherwise both come back `null`. The
 * UI must always fall back to the curated labels, never assume raw identity
 * is present (ADR-0011.1, docs/API_CONTRACTS.md).
 */
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
