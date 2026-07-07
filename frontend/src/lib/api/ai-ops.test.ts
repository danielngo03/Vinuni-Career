/**
 * Unit tests for aiOpsApi — verifies that each method calls the correct
 * backend path and builds the expected query string (including `range_days`
 * as integer, `group_by` in snake_case). The `api` object from `./client`
 * is mocked so no real HTTP calls are made.
 *
 * Contract aligned to the REAL backend:
 * - range_days: int (not a `range` string)
 * - spend/volume return bare lists (AiOpsSpendRow[], AiOpsVolumeRow[])
 * - reliability returns a dict (AiOpsReliability), circuit_states is an object map
 * - events uses api.list and returns AiOpsEventsPage {items, next_cursor}
 * - prices: {provider, model, input_usd_per_1k, output_usd_per_1k, active, updated_at}
 * - platformOverview outbox: {pending, sent, failed, skipped, dead, ...} — no failed_last_hour
 */
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { MockInstance } from "vitest";
import type { ApiListEnvelope } from "@/lib/api/types";

/* -------------------------------------------------------------------------- */
/* Mock the api helper from client.ts                                         */
/* -------------------------------------------------------------------------- */

vi.mock("@/lib/api/client", () => {
  return {
    api: {
      get: vi.fn(),
      post: vi.fn(),
      patch: vi.fn(),
      put: vi.fn(),
      delete: vi.fn(),
      list: vi.fn(),
      health: vi.fn(),
    },
    apiFetch: vi.fn(),
    apiUpload: vi.fn(),
    apiDownload: vi.fn(),
    setTokenSource: vi.fn(),
    setRefreshHandler: vi.fn(),
  };
});

import { api } from "@/lib/api/client";
import {
  aiOpsApi,
  type AiOpsOverview,
  type AiOpsSpendRow,
  type AiOpsReliability,
  type AiOpsVolumeRow,
  type AiOpsEvent,
  type AiOpsPrice,
  type AdminPlatformOverview,
} from "./ai-ops";

const apiGet = api.get as unknown as MockInstance;
const apiPost = api.post as unknown as MockInstance;
const apiPatch = api.patch as unknown as MockInstance;
const apiList = api.list as unknown as MockInstance;

/* -------------------------------------------------------------------------- */
/* Helpers                                                                    */
/* -------------------------------------------------------------------------- */

function resolveWith<T>(mock: MockInstance, value: T): void {
  mock.mockResolvedValueOnce(value);
}

beforeEach(() => {
  vi.clearAllMocks();
});

/* -------------------------------------------------------------------------- */
/* overview — sends range_days (int), not range (string)                      */
/* -------------------------------------------------------------------------- */

describe("aiOpsApi.overview", () => {
  it("sends range_days=1 for 'today'", async () => {
    const stub: AiOpsOverview = {
      spend_today: 0.42,
      budget: 5.0,
      error_rate: 0.01,
      requests: 120,
      p95_latency_ms: 850,
    };
    resolveWith(apiGet, stub);

    const result = await aiOpsApi.overview("today");

    expect(apiGet).toHaveBeenCalledOnce();
    expect(apiGet).toHaveBeenCalledWith("/admin/ai-ops/overview", {
      query: { range_days: 1 },
    });
    expect(result).toEqual(stub);
  });

  it("sends range_days=7 for '7d'", async () => {
    resolveWith(apiGet, {} as AiOpsOverview);
    await aiOpsApi.overview("7d");
    expect(apiGet).toHaveBeenCalledWith("/admin/ai-ops/overview", {
      query: { range_days: 7 },
    });
  });

  it("sends range_days=30 for '30d'", async () => {
    resolveWith(apiGet, {} as AiOpsOverview);
    await aiOpsApi.overview("30d");
    expect(apiGet).toHaveBeenCalledWith("/admin/ai-ops/overview", {
      query: { range_days: 30 },
    });
  });
});

/* -------------------------------------------------------------------------- */
/* spend — returns AiOpsSpendRow[] (bare list), sends range_days              */
/* -------------------------------------------------------------------------- */

describe("aiOpsApi.spend", () => {
  it("sends range_days=30&group_by=model and returns bare list", async () => {
    const stub: AiOpsSpendRow[] = [
      {
        day: null,
        task_type: null,
        provider: null,
        model: "deepseek/v3",
        cost_usd: 0.001,
        requests: 5,
        errors: 0,
      },
    ];
    resolveWith(apiGet, stub);

    const result = await aiOpsApi.spend("30d", "model");

    expect(apiGet).toHaveBeenCalledWith("/admin/ai-ops/spend", {
      query: { range_days: 30, group_by: "model" },
    });
    expect(result).toEqual(stub);
  });

  it("sends group_by=feature (snake_case)", async () => {
    resolveWith(apiGet, [] as AiOpsSpendRow[]);
    await aiOpsApi.spend("7d", "feature");
    const [, opts] = apiGet.mock.calls[0] as [string, { query: Record<string, unknown> }];
    expect(opts.query.group_by).toBe("feature");
    expect(opts.query.range_days).toBe(7);
  });

  it("sends group_by=provider", async () => {
    resolveWith(apiGet, [] as AiOpsSpendRow[]);
    await aiOpsApi.spend("7d", "provider");
    const [, opts] = apiGet.mock.calls[0] as [string, { query: Record<string, unknown> }];
    expect(opts.query.group_by).toBe("provider");
  });
});

/* -------------------------------------------------------------------------- */
/* reliability — returns AiOpsReliability dict (NOT rows array)               */
/* -------------------------------------------------------------------------- */

describe("aiOpsApi.reliability", () => {
  it("calls GET /admin/ai-ops/reliability with range_days", async () => {
    const stub: AiOpsReliability = {
      requests: 100,
      errors: 2,
      fallbacks: 3,
      error_rate: 0.02,
      fallback_rate: 0.03,
      circuit_states: {},
    };
    resolveWith(apiGet, stub);

    const result = await aiOpsApi.reliability("7d", "feature");

    expect(apiGet).toHaveBeenCalledWith("/admin/ai-ops/reliability", {
      query: { range_days: 7, group_by: "feature" },
    });
    expect(result.circuit_states).toBeDefined();
    expect(typeof result.circuit_states).toBe("object");
  });

  it("sends range_days=1 for 'today'", async () => {
    resolveWith(apiGet, {} as AiOpsReliability);
    await aiOpsApi.reliability("today", "feature");
    const [, opts] = apiGet.mock.calls[0] as [string, { query: Record<string, unknown> }];
    expect(opts.query.range_days).toBe(1);
  });
});

/* -------------------------------------------------------------------------- */
/* volume — returns AiOpsVolumeRow[] (bare list)                              */
/* -------------------------------------------------------------------------- */

describe("aiOpsApi.volume", () => {
  it("calls GET /admin/ai-ops/volume with range_days", async () => {
    const stub: AiOpsVolumeRow[] = [
      {
        day: null,
        task_type: "cv_bullets",
        requests: 10,
        prompt_tokens: 500,
        completion_tokens: 200,
      },
    ];
    resolveWith(apiGet, stub);

    await aiOpsApi.volume("today", "feature");

    expect(apiGet).toHaveBeenCalledWith("/admin/ai-ops/volume", {
      query: { range_days: 1, group_by: "feature" },
    });
  });
});

/* -------------------------------------------------------------------------- */
/* events — uses api.list, returns AiOpsEventsPage {items, next_cursor}       */
/* -------------------------------------------------------------------------- */

describe("aiOpsApi.events", () => {
  it("calls api.list (not api.get) and unwraps paginated envelope", async () => {
    const sampleEvent: AiOpsEvent = {
      id: "evt-1",
      created_at: "2026-07-07T10:00:00Z",
      task_type: "cv_bullets",
      alias: "chat_default",
      provider: null,
      model: null,
      prompt_tokens: 100,
      completion_tokens: 50,
      latency_ms: 300,
      cost_usd: 0.001,
      status: "success",
      fallback_used: false,
      circuit_open: false,
      unpriced: false,
      langfuse_trace_id: "trace-abc",
    };
    const envelope: ApiListEnvelope<AiOpsEvent> = {
      data: [sampleEvent],
      page: { next_cursor: "cursor-next", limit: 50 },
    };
    resolveWith(apiList, envelope);

    const result = await aiOpsApi.events({ cursor: undefined, status: "success", limit: 50 });

    expect(apiList).toHaveBeenCalledOnce();
    expect(apiList).toHaveBeenCalledWith("/admin/ai-ops/events", {
      query: { cursor: undefined, status: "success", task_type: undefined, limit: 50 },
    });
    // result is AiOpsEventsPage
    expect(result.items).toEqual([sampleEvent]);
    expect(result.next_cursor).toBe("cursor-next");
  });

  it("returns empty items and null next_cursor when no events", async () => {
    const envelope: ApiListEnvelope<AiOpsEvent> = {
      data: [],
      page: { next_cursor: null, limit: 50 },
    };
    resolveWith(apiList, envelope);

    const result = await aiOpsApi.events();

    expect(result.items).toEqual([]);
    expect(result.next_cursor).toBeNull();
  });

  it("does NOT send a range param (not a backend param)", async () => {
    const envelope: ApiListEnvelope<AiOpsEvent> = {
      data: [],
      page: { next_cursor: null, limit: 50 },
    };
    resolveWith(apiList, envelope);

    await aiOpsApi.events({ limit: 25 });

    const [, opts] = apiList.mock.calls[0] as [string, { query: Record<string, unknown> }];
    expect("range" in opts.query).toBe(false);
    expect("range_days" in opts.query).toBe(false);
  });

  it("exposes langfuse_trace_id on event items", async () => {
    const withTrace: AiOpsEvent = {
      id: "evt-trace",
      created_at: "2026-07-07T10:00:00Z",
      task_type: "job_fit",
      alias: "chat_default",
      provider: null,
      model: null,
      prompt_tokens: null,
      completion_tokens: null,
      latency_ms: null,
      cost_usd: null,
      status: "success",
      fallback_used: false,
      circuit_open: false,
      unpriced: true,
      langfuse_trace_id: "lf-trace-xyz",
    };
    const envelope: ApiListEnvelope<AiOpsEvent> = {
      data: [withTrace],
      page: { next_cursor: null, limit: 50 },
    };
    resolveWith(apiList, envelope);

    const result = await aiOpsApi.events();
    const firstItem = result.items[0];
    expect(firstItem).toBeDefined();
    expect(firstItem?.langfuse_trace_id).toBe("lf-trace-xyz");
  });
});

/* -------------------------------------------------------------------------- */
/* prices — real backend fields                                                */
/* -------------------------------------------------------------------------- */

describe("aiOpsApi.prices", () => {
  it("calls GET /admin/ai-ops/prices", async () => {
    resolveWith(apiGet, [] as AiOpsPrice[]);
    await aiOpsApi.prices();
    expect(apiGet).toHaveBeenCalledOnce();
    const [path] = apiGet.mock.calls[0] as [string];
    expect(path).toBe("/admin/ai-ops/prices");
  });
});

/* -------------------------------------------------------------------------- */
/* createPrice — real body fields                                              */
/* -------------------------------------------------------------------------- */

describe("aiOpsApi.createPrice", () => {
  it("POSTs to /admin/ai-ops/prices with real field names", async () => {
    const body = {
      provider: "openrouter",
      model: "deepseek/deepseek-v3",
      input_usd_per_1k: 0.0015,
      output_usd_per_1k: 0.002,
      active: true,
    };
    const stub: AiOpsPrice = {
      id: "price-1",
      provider: "openrouter",
      model: "deepseek/deepseek-v3",
      input_usd_per_1k: 0.0015,
      output_usd_per_1k: 0.002,
      active: true,
      updated_by: null,
      updated_at: "2026-07-07T00:00:00Z",
    };
    resolveWith(apiPost, stub);

    const result = await aiOpsApi.createPrice(body);

    expect(apiPost).toHaveBeenCalledOnce();
    expect(apiPost).toHaveBeenCalledWith("/admin/ai-ops/prices", body);
    expect(result).toEqual(stub);
  });
});

/* -------------------------------------------------------------------------- */
/* updatePrice — real patch fields                                             */
/* -------------------------------------------------------------------------- */

describe("aiOpsApi.updatePrice", () => {
  it("PATCHes /admin/ai-ops/prices/{id} with real field names", async () => {
    const id = "price-42";
    const body = { input_usd_per_1k: 0.002, active: false };
    const stub: AiOpsPrice = {
      id,
      provider: "openrouter",
      model: "deepseek/deepseek-v3",
      input_usd_per_1k: 0.002,
      output_usd_per_1k: 0.002,
      active: false,
      updated_by: "user-uuid",
      updated_at: "2026-07-07T00:00:00Z",
    };
    resolveWith(apiPatch, stub);

    const result = await aiOpsApi.updatePrice(id, body);

    expect(apiPatch).toHaveBeenCalledOnce();
    expect(apiPatch).toHaveBeenCalledWith(`/admin/ai-ops/prices/${id}`, body);
    expect(result).toEqual(stub);
  });
});

/* -------------------------------------------------------------------------- */
/* platformOverview — real outbox fields (no failed_last_hour)                */
/* -------------------------------------------------------------------------- */

describe("aiOpsApi.platformOverview", () => {
  it("calls GET /admin/overview", async () => {
    const stub: AdminPlatformOverview = {
      ai: {
        spend_today: 1.23,
        budget: 5.0,
        error_rate: 0.02,
        requests: 500,
        p95_latency_ms: null,
      },
      outbox: {
        pending: 4,
        sent: 100,
        failed: 2,
        skipped: 0,
        dead: 0,
        oldest_pending_age_seconds: 120,
        retry_scheduled: 1,
      },
      moderation_pending: 2,
      active_users: 130,
    };
    resolveWith(apiGet, stub);

    const result = await aiOpsApi.platformOverview();

    expect(apiGet).toHaveBeenCalledOnce();
    const [path] = apiGet.mock.calls[0] as [string];
    expect(path).toBe("/admin/overview");
    expect(result.outbox.failed).toBe(2);
    // Confirm no failed_last_hour field
    expect("failed_last_hour" in result.outbox).toBe(false);
    expect(result).toEqual(stub);
  });
});
