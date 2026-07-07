/**
 * Unit tests for aiOpsApi — verifies that each method calls the correct
 * backend path and builds the expected query string (including snake_case
 * `group_by` as the backend requires). The `api` object from `./client`
 * is mocked so no real HTTP calls are made.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { MockInstance } from "vitest";

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
  type AiOpsSpendResponse,
  type AiOpsReliabilityResponse,
  type AiOpsVolumeResponse,
  type AiOpsEventsResponse,
  type AiOpsPrice,
  type AdminPlatformOverview,
} from "./ai-ops";

const apiGet = api.get as unknown as MockInstance;
const apiPost = api.post as unknown as MockInstance;
const apiPatch = api.patch as unknown as MockInstance;

/* -------------------------------------------------------------------------- */
/* Helpers                                                                    */
/* -------------------------------------------------------------------------- */

/** Resolve the mocked api.get/post/patch with a typed stub. */
function resolveWith<T>(mock: MockInstance, value: T): void {
  mock.mockResolvedValueOnce(value);
}

beforeEach(() => {
  vi.clearAllMocks();
});

/* -------------------------------------------------------------------------- */
/* overview                                                                   */
/* -------------------------------------------------------------------------- */

describe("aiOpsApi.overview", () => {
  it("calls GET /admin/ai-ops/overview with range query param", async () => {
    const stub: AiOpsOverview = {
      spend_today: "0.42",
      budget: "5.00",
      error_rate: 0.01,
      requests: 120,
      total_tokens: 45000,
      avg_latency_ms: 320,
      updated_at: null,
    };
    resolveWith(apiGet, stub);

    const result = await aiOpsApi.overview("7d");

    expect(apiGet).toHaveBeenCalledOnce();
    expect(apiGet).toHaveBeenCalledWith("/admin/ai-ops/overview", {
      query: { range: "7d" },
    });
    expect(result).toEqual(stub);
  });

  it("passes 'today' range correctly", async () => {
    resolveWith(apiGet, {} as AiOpsOverview);
    await aiOpsApi.overview("today");
    expect(apiGet).toHaveBeenCalledWith("/admin/ai-ops/overview", {
      query: { range: "today" },
    });
  });

  it("passes '30d' range correctly", async () => {
    resolveWith(apiGet, {} as AiOpsOverview);
    await aiOpsApi.overview("30d");
    expect(apiGet).toHaveBeenCalledWith("/admin/ai-ops/overview", {
      query: { range: "30d" },
    });
  });
});

/* -------------------------------------------------------------------------- */
/* spend                                                                      */
/* -------------------------------------------------------------------------- */

describe("aiOpsApi.spend", () => {
  it("includes range=30d&group_by=model in the query", async () => {
    const stub: AiOpsSpendResponse = {
      range: "30d",
      group_by: "model",
      rows: [],
    };
    resolveWith(apiGet, stub);

    const result = await aiOpsApi.spend("30d", "model");

    expect(apiGet).toHaveBeenCalledWith("/admin/ai-ops/spend", {
      query: { range: "30d", group_by: "model" },
    });
    expect(result).toEqual(stub);
  });

  it("sends group_by=feature (snake_case) for feature grouping", async () => {
    resolveWith(apiGet, {} as AiOpsSpendResponse);
    await aiOpsApi.spend("7d", "feature");
    const [, opts] = apiGet.mock.calls[0] as [string, { query: Record<string, string> }];
    expect(opts.query.group_by).toBe("feature");
  });

  it("sends group_by=provider for provider grouping", async () => {
    resolveWith(apiGet, {} as AiOpsSpendResponse);
    await aiOpsApi.spend("7d", "provider");
    const [, opts] = apiGet.mock.calls[0] as [string, { query: Record<string, string> }];
    expect(opts.query.group_by).toBe("provider");
  });
});

/* -------------------------------------------------------------------------- */
/* reliability                                                                */
/* -------------------------------------------------------------------------- */

describe("aiOpsApi.reliability", () => {
  it("calls GET /admin/ai-ops/reliability with correct params", async () => {
    const stub: AiOpsReliabilityResponse = {
      range: "7d",
      group_by: "feature",
      rows: [],
      circuit_states: [],
    };
    resolveWith(apiGet, stub);

    await aiOpsApi.reliability("7d", "feature");

    expect(apiGet).toHaveBeenCalledWith("/admin/ai-ops/reliability", {
      query: { range: "7d", group_by: "feature" },
    });
  });
});

/* -------------------------------------------------------------------------- */
/* volume                                                                     */
/* -------------------------------------------------------------------------- */

describe("aiOpsApi.volume", () => {
  it("calls GET /admin/ai-ops/volume with correct params", async () => {
    const stub: AiOpsVolumeResponse = {
      range: "today",
      group_by: "provider",
      rows: [],
    };
    resolveWith(apiGet, stub);

    await aiOpsApi.volume("today", "provider");

    expect(apiGet).toHaveBeenCalledWith("/admin/ai-ops/volume", {
      query: { range: "today", group_by: "provider" },
    });
  });
});

/* -------------------------------------------------------------------------- */
/* events                                                                     */
/* -------------------------------------------------------------------------- */

describe("aiOpsApi.events", () => {
  it("calls GET /admin/ai-ops/events with no params when called with defaults", async () => {
    const stub: AiOpsEventsResponse = { data: [], next_cursor: null, limit: 50 };
    resolveWith(apiGet, stub);

    await aiOpsApi.events();

    expect(apiGet).toHaveBeenCalledWith("/admin/ai-ops/events", {
      query: {
        cursor: undefined,
        range: undefined,
        alias: undefined,
        status: undefined,
        task_type: undefined,
        limit: undefined,
      },
    });
  });

  it("passes cursor and filter params through", async () => {
    resolveWith(apiGet, {} as AiOpsEventsResponse);
    await aiOpsApi.events({ cursor: "abc123", range: "30d", status: "error", limit: 25 });
    expect(apiGet).toHaveBeenCalledWith("/admin/ai-ops/events", {
      query: {
        cursor: "abc123",
        range: "30d",
        alias: undefined,
        status: "error",
        task_type: undefined,
        limit: 25,
      },
    });
  });
});

/* -------------------------------------------------------------------------- */
/* prices                                                                     */
/* -------------------------------------------------------------------------- */

describe("aiOpsApi.prices", () => {
  it("calls GET /admin/ai-ops/prices", async () => {
    resolveWith(apiGet, [] as AiOpsPrice[]);
    await aiOpsApi.prices();
    // api.get is called with path only (no options object)
    expect(apiGet).toHaveBeenCalledOnce();
    const [path] = apiGet.mock.calls[0] as [string];
    expect(path).toBe("/admin/ai-ops/prices");
  });
});

/* -------------------------------------------------------------------------- */
/* createPrice                                                                */
/* -------------------------------------------------------------------------- */

describe("aiOpsApi.createPrice", () => {
  it("POSTs to /admin/ai-ops/prices with body", async () => {
    const body = {
      alias: "chat_cheap",
      prompt_cost_per_1k: "0.00015",
      completion_cost_per_1k: "0.00060",
      effective_from: "2026-01-01T00:00:00Z",
    };
    const stub: AiOpsPrice = {
      id: "price-1",
      alias: "chat_cheap",
      prompt_cost_per_1k: "0.00015",
      completion_cost_per_1k: "0.00060",
      effective_from: "2026-01-01T00:00:00Z",
      effective_until: null,
      notes: null,
      created_at: "2026-01-01T00:00:00Z",
      updated_at: null,
    };
    resolveWith(apiPost, stub);

    const result = await aiOpsApi.createPrice(body);

    expect(apiPost).toHaveBeenCalledOnce();
    expect(apiPost).toHaveBeenCalledWith("/admin/ai-ops/prices", body);
    expect(result).toEqual(stub);
  });
});

/* -------------------------------------------------------------------------- */
/* updatePrice                                                                */
/* -------------------------------------------------------------------------- */

describe("aiOpsApi.updatePrice", () => {
  it("PATCHes /admin/ai-ops/prices/{id} with partial body", async () => {
    const id = "price-42";
    const body = { notes: "Updated for Q3" };
    const stub: AiOpsPrice = {
      id,
      alias: "chat_cheap",
      prompt_cost_per_1k: "0.00015",
      completion_cost_per_1k: "0.00060",
      effective_from: "2026-01-01T00:00:00Z",
      effective_until: null,
      notes: "Updated for Q3",
      created_at: "2026-01-01T00:00:00Z",
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
/* platformOverview                                                           */
/* -------------------------------------------------------------------------- */

describe("aiOpsApi.platformOverview", () => {
  it("calls GET /admin/overview", async () => {
    const stub: AdminPlatformOverview = {
      ai: { spend_today: "1.23", error_rate: 0.02, requests: 500 },
      outbox: { pending: 4, failed_last_hour: 0 },
      moderation_pending: 2,
      active_users: 130,
    };
    resolveWith(apiGet, stub);

    const result = await aiOpsApi.platformOverview();

    // api.get is called with path only (no options object)
    expect(apiGet).toHaveBeenCalledOnce();
    const [path] = apiGet.mock.calls[0] as [string];
    expect(path).toBe("/admin/overview");
    expect(result).toEqual(stub);
  });
});
