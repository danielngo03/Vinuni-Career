import { api } from "./client";
import type { ApiListEnvelope } from "./types";

/* -------------------------------------------------------------------------- */
/* Shared range + group_by vocabulary                                         */
/* -------------------------------------------------------------------------- */

export type AiOpsRange = "today" | "7d" | "30d";
export type AiOpsGroupBy = "feature" | "model" | "provider";

/** Map the UI range token to the integer the backend expects for `range_days`. */
function rangeToDays(range: AiOpsRange): number {
  if (range === "today") return 1;
  if (range === "7d") return 7;
  return 30;
}

/* -------------------------------------------------------------------------- */
/* Overview                                                                   */
/* -------------------------------------------------------------------------- */

/**
 * Response for `GET /admin/ai-ops/overview`.
 * Real backend fields — provider/model identity is never exposed at this level.
 *
 * spend_today / budget are numbers (float/int), NOT strings.
 * p95_latency_ms is null when no events exist in the window.
 */
export interface AiOpsOverview {
  spend_today: number;
  budget: number;
  error_rate: number;
  requests: number;
  p95_latency_ms: number | null;
}

/* -------------------------------------------------------------------------- */
/* Spend                                                                      */
/* -------------------------------------------------------------------------- */

/**
 * One row from `GET /admin/ai-ops/spend`.
 * Real backend fields (bare list inside `data` envelope).
 * `provider` and `model` are `null` when identity is masked.
 * `day` is an ISO date string or `null` for grouped (non-day-grain) rows.
 */
export interface AiOpsSpendRow {
  day: string | null;
  task_type: string | null;
  provider: string | null;
  model: string | null;
  cost_usd: number;
  requests: number;
  errors: number;
}

/* -------------------------------------------------------------------------- */
/* Reliability                                                                */
/* -------------------------------------------------------------------------- */

/**
 * `circuit_states` from `GET /admin/ai-ops/reliability` is an object map
 * `{ [key: string]: CircuitStateValue }` — NOT an array.
 * Keys are either real provider names (with identity grant) or positional
 * placeholders (`"provider_1"`, …) when masked.
 * `get_circuit_state()` in the gateway returns the raw Python dict stored in
 * `_circuit_states`; the shape is whatever the factory stores (typically a
 * simple string state or a richer struct — we accept `unknown` and render
 * defensively).
 */
export interface AiOpsReliability {
  requests: number;
  errors: number;
  fallbacks: number;
  error_rate: number;
  fallback_rate: number;
  circuit_states: Record<string, unknown>;
}

/* -------------------------------------------------------------------------- */
/* Volume                                                                     */
/* -------------------------------------------------------------------------- */

/**
 * One row from `GET /admin/ai-ops/volume`.
 * Real backend fields (bare list inside `data` envelope).
 * `day` is ISO date or null for grouped rows.
 */
export interface AiOpsVolumeRow {
  day: string | null;
  task_type: string | null;
  requests: number;
  prompt_tokens: number;
  completion_tokens: number;
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
 * One row from `GET /admin/ai-ops/events`. Cursor-paginated via `paginated()`.
 * `provider` and `model` are `null` when masked by secrecy policy.
 * `langfuse_trace_id` is `null` when observability is disabled or not set.
 * `cost_usd` is a number or null (not a string).
 * `prompt_tokens` / `completion_tokens` / `latency_ms` may be null.
 */
export interface AiOpsEvent {
  id: string;
  created_at: string;
  task_type: string;
  alias: string;
  provider: string | null;
  model: string | null;
  prompt_tokens: number | null;
  completion_tokens: number | null;
  latency_ms: number | null;
  cost_usd: number | null;
  status: AiOpsEventStatus;
  fallback_used: boolean;
  circuit_open: boolean;
  unpriced: boolean;
  langfuse_trace_id: string | null;
}

export interface AiOpsEventsParams {
  cursor?: string;
  range?: AiOpsRange;
  status?: AiOpsEventStatus;
  task_type?: string;
  limit?: number;
}

/** The unwrapped events list envelope — items + pagination cursor. */
export interface AiOpsEventsPage {
  items: AiOpsEvent[];
  next_cursor: string | null;
}

/* -------------------------------------------------------------------------- */
/* Prices                                                                     */
/* -------------------------------------------------------------------------- */

/**
 * One token-price row managed by the admin (`GET /admin/ai-ops/prices`).
 * Real backend fields from `pricing_admin_service._row_snapshot`.
 * Prices are cost per 1 000 tokens in USD (numbers, not strings at rest,
 * but Pydantic/JSON serialises Numeric as float).
 */
export interface AiOpsPrice {
  id: string;
  provider: string;
  model: string;
  input_usd_per_1k: number;
  output_usd_per_1k: number;
  active: boolean;
  updated_by: string | null;
  updated_at: string;
}

export interface AiOpsPriceCreateBody {
  provider: string;
  model: string;
  input_usd_per_1k: number;
  output_usd_per_1k: number;
  active?: boolean;
}

export interface AiOpsPriceUpdateBody {
  provider?: string;
  model?: string;
  input_usd_per_1k?: number;
  output_usd_per_1k?: number;
  active?: boolean;
}

/* -------------------------------------------------------------------------- */
/* Platform admin overview                                                    */
/* -------------------------------------------------------------------------- */

/**
 * Response for `GET /admin/overview`.
 * Real backend fields from `platform_overview.platform_overview()`.
 *
 * `ai` sub-section is the `overview()` result (spend_today, budget, etc.).
 * `outbox` sub-section comes from `dispatch_service.status_counts()` plus
 * `oldest_pending_age_seconds` and `retry_scheduled`. The `failed` key is the
 * cumulative failed count — there is no `failed_last_hour` key.
 */
export interface AdminPlatformOverview {
  ai: {
    spend_today: number;
    budget: number;
    error_rate: number;
    requests: number;
    p95_latency_ms: number | null;
  };
  outbox: {
    pending: number;
    sent: number;
    failed: number;
    skipped: number;
    dead: number;
    oldest_pending_age_seconds: number | null;
    retry_scheduled: number;
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
   * `GET /admin/ai-ops/overview?range_days=<N>`
   * Backend param is `range_days: int`, not a `range` string.
   */
  overview(range: AiOpsRange): Promise<AiOpsOverview> {
    return api.get<AiOpsOverview>("/admin/ai-ops/overview", {
      query: { range_days: rangeToDays(range) },
    });
  },

  /**
   * Cost distribution breakdown.
   * `GET /admin/ai-ops/spend?range_days=<N>&group_by=<groupBy>`
   * Returns a bare list (unwrapped from `success({data: []})` by `api.get`).
   */
  spend(range: AiOpsRange, groupBy: AiOpsGroupBy): Promise<AiOpsSpendRow[]> {
    return api.get<AiOpsSpendRow[]>("/admin/ai-ops/spend", {
      query: { range_days: rangeToDays(range), group_by: groupBy },
    });
  },

  /**
   * Error/fallback rates and circuit-breaker states.
   * `GET /admin/ai-ops/reliability?range_days=<N>&group_by=<groupBy>`
   * Returns a dict (NOT rows array).
   */
  reliability(
    range: AiOpsRange,
    groupBy: AiOpsGroupBy,
  ): Promise<AiOpsReliability> {
    return api.get<AiOpsReliability>("/admin/ai-ops/reliability", {
      query: { range_days: rangeToDays(range), group_by: groupBy },
    });
  },

  /**
   * Request and token volume breakdown.
   * `GET /admin/ai-ops/volume?range_days=<N>&group_by=<groupBy>`
   * Returns a bare list.
   */
  volume(range: AiOpsRange, groupBy: AiOpsGroupBy): Promise<AiOpsVolumeRow[]> {
    return api.get<AiOpsVolumeRow[]>("/admin/ai-ops/volume", {
      query: { range_days: rangeToDays(range), group_by: groupBy },
    });
  },

  /**
   * Cursor-paginated raw AI call events.
   * `GET /admin/ai-ops/events?cursor=&status=&task_type=&limit=`
   * Uses `api.list` to get the full `paginated()` envelope:
   *   `{ data: AiOpsEvent[], page: { next_cursor, limit } }`.
   *
   * Note: `range` is NOT a backend param. The backend filters by cursor/status/task_type only.
   */
  async events(params: AiOpsEventsParams = {}): Promise<AiOpsEventsPage> {
    const { cursor, status, task_type, limit } = params;
    const envelope: ApiListEnvelope<AiOpsEvent> = await api.list<AiOpsEvent>(
      "/admin/ai-ops/events",
      {
        query: { cursor, status, task_type, limit },
      },
    );
    return {
      items: envelope.data,
      next_cursor: envelope.page.next_cursor,
    };
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
