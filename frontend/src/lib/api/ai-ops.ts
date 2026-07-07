import { api } from "./client";

/* -------------------------------------------------------------------------- */
/* Shared range + group_by vocabulary                                         */
/* -------------------------------------------------------------------------- */

export type AiOpsRange = "today" | "7d" | "30d";
export type AiOpsGroupBy = "feature" | "model" | "provider";

/* -------------------------------------------------------------------------- */
/* Overview                                                                   */
/* -------------------------------------------------------------------------- */

/**
 * Response for `GET /admin/ai-ops/overview`. All monetary values are USD as
 * decimal strings; counts are integers; error_rate is a 0–1 float.
 * Provider/model identity is never exposed at this level.
 */
export interface AiOpsOverview {
  spend_today: string;
  budget: string;
  error_rate: number;
  requests: number;
  /** Total completion tokens consumed in the range. */
  total_tokens: number;
  /** Average latency across all AI calls in ms. */
  avg_latency_ms: number;
  updated_at: string | null;
}

/* -------------------------------------------------------------------------- */
/* Spend                                                                      */
/* -------------------------------------------------------------------------- */

/**
 * One row from `GET /admin/ai-ops/spend`. `provider` and `model` are `null`
 * when the identity is masked (operator-defined secrecy policy).
 */
export interface AiOpsSpendRow {
  ts: string;
  /** Grouping key: feature slug, alias name, or provider name — never raw ids. */
  group: string;
  cost_usd: string;
  requests: number;
  provider: string | null;
  model: string | null;
}

export interface AiOpsSpendResponse {
  range: AiOpsRange;
  group_by: AiOpsGroupBy;
  rows: AiOpsSpendRow[];
}

/* -------------------------------------------------------------------------- */
/* Reliability                                                                */
/* -------------------------------------------------------------------------- */

export interface AiOpsCircuitState {
  alias: string;
  state: "closed" | "open" | "half_open";
  failures: number;
  last_failure_at: string | null;
}

export interface AiOpsReliabilityRow {
  group: string;
  error_rate: number;
  fallback_rate: number;
  /** p50 latency in ms. */
  p50_ms: number;
  /** p95 latency in ms. */
  p95_ms: number;
  /** p99 latency in ms. */
  p99_ms: number;
  provider: string | null;
  model: string | null;
}

export interface AiOpsReliabilityResponse {
  range: AiOpsRange;
  group_by: AiOpsGroupBy;
  rows: AiOpsReliabilityRow[];
  circuit_states: AiOpsCircuitState[];
}

/* -------------------------------------------------------------------------- */
/* Volume                                                                     */
/* -------------------------------------------------------------------------- */

export interface AiOpsVolumeRow {
  ts: string;
  group: string;
  requests: number;
  prompt_tokens: number;
  completion_tokens: number;
  provider: string | null;
  model: string | null;
}

export interface AiOpsVolumeResponse {
  range: AiOpsRange;
  group_by: AiOpsGroupBy;
  rows: AiOpsVolumeRow[];
}

/* -------------------------------------------------------------------------- */
/* Events (cursor-paginated)                                                  */
/* -------------------------------------------------------------------------- */

export type AiOpsEventStatus =
  | "success"
  | "error"
  | "fallback"
  | "rate_limited"
  | "timeout";

/**
 * One row from `GET /admin/ai-ops/events`. Cursor-paginated.
 * `provider` and `model` are `null` when masked by secrecy policy.
 * `langfuse_trace_id` is `null` when observability is disabled.
 */
export interface AiOpsEvent {
  id: string;
  created_at: string;
  task_type: string;
  alias: string;
  provider: string | null;
  model: string | null;
  prompt_tokens: number;
  completion_tokens: number;
  latency_ms: number;
  cost_usd: string;
  status: AiOpsEventStatus;
  langfuse_trace_id: string | null;
}

export interface AiOpsEventsParams {
  cursor?: string;
  range?: AiOpsRange;
  alias?: string;
  status?: AiOpsEventStatus;
  task_type?: string;
  limit?: number;
}

export interface AiOpsEventsResponse {
  data: AiOpsEvent[];
  next_cursor: string | null;
  limit: number;
}

/* -------------------------------------------------------------------------- */
/* Prices                                                                     */
/* -------------------------------------------------------------------------- */

/**
 * One token-price row managed by the admin (`GET /admin/ai-ops/prices`).
 * Prices are stored as cost per 1 000 tokens in USD.
 */
export interface AiOpsPrice {
  id: string;
  alias: string;
  prompt_cost_per_1k: string;
  completion_cost_per_1k: string;
  effective_from: string;
  effective_until: string | null;
  notes: string | null;
  created_at: string;
  updated_at: string | null;
}

export interface AiOpsPriceCreateBody {
  alias: string;
  prompt_cost_per_1k: string;
  completion_cost_per_1k: string;
  effective_from: string;
  effective_until?: string;
  notes?: string;
}

export interface AiOpsPriceUpdateBody {
  prompt_cost_per_1k?: string;
  completion_cost_per_1k?: string;
  effective_from?: string;
  effective_until?: string | null;
  notes?: string | null;
}

/* -------------------------------------------------------------------------- */
/* Platform admin overview                                                    */
/* -------------------------------------------------------------------------- */

/**
 * Response for `GET /admin/overview`. Gives a cross-domain health snapshot
 * for the super-admin landing surface.
 */
export interface AdminPlatformOverview {
  ai: {
    spend_today: string;
    error_rate: number;
    requests: number;
  };
  outbox: {
    pending: number;
    failed_last_hour: number;
  };
  moderation_pending: number;
  active_users: number;
}

/* -------------------------------------------------------------------------- */
/* API object                                                                 */
/* -------------------------------------------------------------------------- */

export const aiOpsApi = {
  /**
   * Aggregate platform AI health for the given range.
   * `GET /admin/ai-ops/overview?range=<range>`
   */
  overview(range: AiOpsRange): Promise<AiOpsOverview> {
    return api.get<AiOpsOverview>("/admin/ai-ops/overview", {
      query: { range },
    });
  },

  /**
   * Cost distribution time-series grouped by feature, model, or provider.
   * `GET /admin/ai-ops/spend?range=<range>&group_by=<groupBy>`
   * NOTE: `group_by` is snake_case as the backend expects it.
   */
  spend(range: AiOpsRange, groupBy: AiOpsGroupBy): Promise<AiOpsSpendResponse> {
    return api.get<AiOpsSpendResponse>("/admin/ai-ops/spend", {
      query: { range, group_by: groupBy },
    });
  },

  /**
   * Error/fallback rates, latency percentiles, and circuit-breaker states.
   * `GET /admin/ai-ops/reliability?range=<range>&group_by=<groupBy>`
   */
  reliability(
    range: AiOpsRange,
    groupBy: AiOpsGroupBy,
  ): Promise<AiOpsReliabilityResponse> {
    return api.get<AiOpsReliabilityResponse>("/admin/ai-ops/reliability", {
      query: { range, group_by: groupBy },
    });
  },

  /**
   * Request and token volume time-series.
   * `GET /admin/ai-ops/volume?range=<range>&group_by=<groupBy>`
   */
  volume(range: AiOpsRange, groupBy: AiOpsGroupBy): Promise<AiOpsVolumeResponse> {
    return api.get<AiOpsVolumeResponse>("/admin/ai-ops/volume", {
      query: { range, group_by: groupBy },
    });
  },

  /**
   * Cursor-paginated raw AI call events.
   * `GET /admin/ai-ops/events?cursor=&range=&alias=&status=&task_type=&limit=`
   */
  events(params: AiOpsEventsParams = {}): Promise<AiOpsEventsResponse> {
    const { cursor, range, alias, status, task_type, limit } = params;
    return api.get<AiOpsEventsResponse>("/admin/ai-ops/events", {
      query: { cursor, range, alias, status, task_type, limit },
    });
  },

  /**
   * List all configured token-price rows.
   * `GET /admin/ai-ops/prices`
   */
  prices(): Promise<AiOpsPrice[]> {
    return api.get<AiOpsPrice[]>("/admin/ai-ops/prices");
  },

  /**
   * Create a new price row.
   * `POST /admin/ai-ops/prices`
   */
  createPrice(body: AiOpsPriceCreateBody): Promise<AiOpsPrice> {
    return api.post<AiOpsPrice>("/admin/ai-ops/prices", body);
  },

  /**
   * Partially update an existing price row.
   * `PATCH /admin/ai-ops/prices/{id}`
   */
  updatePrice(id: string, body: AiOpsPriceUpdateBody): Promise<AiOpsPrice> {
    return api.patch<AiOpsPrice>(`/admin/ai-ops/prices/${id}`, body);
  },

  /**
   * Super-admin cross-domain health snapshot.
   * `GET /admin/overview`
   */
  platformOverview(): Promise<AdminPlatformOverview> {
    return api.get<AdminPlatformOverview>("/admin/overview");
  },
};
