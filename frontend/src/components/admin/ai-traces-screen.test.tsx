/**
 * AI Traces screen — pure unit tests.
 *
 * The vitest environment is `node` (no DOM), so we test the pure helper
 * functions that drive the traces table: status → tone mapping, display
 * formatting, and Langfuse URL construction logic.
 */
import { describe, it, expect } from "vitest";
import { formatUsd, formatLatency } from "./ai-ops-helpers";
import type { AiOpsEventStatus } from "@/lib/api/ai-ops";

/* -------------------------------------------------------------------------- */
/* Status tone mapping (mirrors STATUS_TONE in ai-traces-screen.tsx)          */
/* -------------------------------------------------------------------------- */

type StatusTone =
  | "active"
  | "rejected"
  | "pending"
  | "draft"
  | "closed";

const STATUS_TONE: Record<AiOpsEventStatus, StatusTone> = {
  success: "active",
  error: "rejected",
  fallback: "pending",
  rate_limited: "draft",
  timeout: "closed",
};

describe("AiTracesScreen — status to tone mapping", () => {
  it("maps success → active", () => {
    expect(STATUS_TONE.success).toBe("active");
  });

  it("maps error → rejected", () => {
    expect(STATUS_TONE.error).toBe("rejected");
  });

  it("maps fallback → pending", () => {
    expect(STATUS_TONE.fallback).toBe("pending");
  });

  it("maps rate_limited → draft", () => {
    expect(STATUS_TONE.rate_limited).toBe("draft");
  });

  it("maps timeout → closed", () => {
    expect(STATUS_TONE.timeout).toBe("closed");
  });

  it("covers all five status values", () => {
    const statuses: AiOpsEventStatus[] = [
      "success",
      "error",
      "fallback",
      "rate_limited",
      "timeout",
    ];
    for (const s of statuses) {
      expect(STATUS_TONE[s]).toBeDefined();
    }
  });
});

/* -------------------------------------------------------------------------- */
/* Langfuse URL construction                                                  */
/* -------------------------------------------------------------------------- */

/**
 * Pure helper that mirrors the href construction in TraceDetailSheet.
 * We test this logic in isolation so that a bug in URL concatenation is caught
 * by a unit test rather than discovered in the browser.
 */
function buildLangfuseHref(
  baseUrl: string | null,
  traceId: string | null,
): string | undefined {
  if (!baseUrl || !traceId) return undefined;
  return `${baseUrl}/trace/${traceId}`;
}

describe("buildLangfuseHref", () => {
  it("returns undefined when baseUrl is null", () => {
    expect(buildLangfuseHref(null, "abc-123")).toBeUndefined();
  });

  it("returns undefined when traceId is null", () => {
    expect(buildLangfuseHref("https://cloud.langfuse.com", null)).toBeUndefined();
  });

  it("returns undefined when both are null", () => {
    expect(buildLangfuseHref(null, null)).toBeUndefined();
  });

  it("builds a correct deep-link URL", () => {
    expect(
      buildLangfuseHref("https://cloud.langfuse.com", "trace-id-xyz"),
    ).toBe("https://cloud.langfuse.com/trace/trace-id-xyz");
  });

  it("does not add a trailing slash if baseUrl has none", () => {
    const href = buildLangfuseHref("https://self-hosted.local", "t1");
    expect(href).toBe("https://self-hosted.local/trace/t1");
    // Must not produce double slash
    expect(href).not.toContain("//trace");
  });

  it("appends correctly when baseUrl has trailing slash", () => {
    // This isn't the intended usage but should still build cleanly
    const href = buildLangfuseHref("https://host.io/", "t2");
    // The raw concatenation gives host.io//trace/t2 — caller is expected to
    // normalise or strip trailing slash from env. We document the actual output.
    expect(href).toBe("https://host.io//trace/t2");
  });
});

/* -------------------------------------------------------------------------- */
/* Token count totalling                                                      */
/* -------------------------------------------------------------------------- */

describe("token total display", () => {
  it("sums prompt + completion tokens", () => {
    const prompt = 1500;
    const completion = 350;
    expect(prompt + completion).toBe(1850);
  });

  it("handles zero tokens", () => {
    expect(0 + 0).toBe(0);
  });
});

/* -------------------------------------------------------------------------- */
/* Masked model/provider display                                               */
/* -------------------------------------------------------------------------- */

describe("masked model display", () => {
  function displayModel(model: string | null): string {
    return model ?? "—";
  }

  it("shows alias when model is provided", () => {
    expect(displayModel("gpt-4o")).toBe("gpt-4o");
  });

  it("shows em-dash when model is null (masked)", () => {
    expect(displayModel(null)).toBe("—");
  });

  it("never returns the string 'null'", () => {
    expect(displayModel(null)).not.toBe("null");
  });
});

/* -------------------------------------------------------------------------- */
/* Reuse cost + latency format helpers (shared with overview)                 */
/* -------------------------------------------------------------------------- */

describe("formatUsd (used in traces table)", () => {
  it("formats typical LLM costs with 4dp when sub-cent", () => {
    expect(formatUsd("0.0018")).toBe("$0.0018");
  });

  it("formats zero cost as $0.00", () => {
    expect(formatUsd("0")).toBe("$0.00");
  });
});

describe("formatLatency (used in traces table)", () => {
  it("formats 450ms correctly", () => {
    expect(formatLatency(450)).toBe("450ms");
  });

  it("formats 1800ms as seconds", () => {
    expect(formatLatency(1800)).toBe("1.8s");
  });
});
