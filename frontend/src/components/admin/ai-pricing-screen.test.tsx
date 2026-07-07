/**
 * AI Pricing screen — pure unit tests.
 *
 * The vitest environment is `node` (no DOM), so we test the pure helper
 * functions and pure logic that drive the pricing table and form validation.
 */
import { describe, it, expect } from "vitest";
import { formatUsd } from "./ai-ops-helpers";
import type { AiOpsPrice } from "@/lib/api/ai-ops";

/* -------------------------------------------------------------------------- */
/* Cost validation (mirrors isValidCost in ai-pricing-screen.tsx)             */
/* -------------------------------------------------------------------------- */

function isValidCost(s: string): boolean {
  const n = parseFloat(s);
  return isFinite(n) && n >= 0;
}

describe("isValidCost", () => {
  it("accepts valid decimal strings", () => {
    expect(isValidCost("0.0015")).toBe(true);
    expect(isValidCost("0.002")).toBe(true);
    expect(isValidCost("1.5")).toBe(true);
    expect(isValidCost("0")).toBe(true);
  });

  it("accepts integer strings", () => {
    expect(isValidCost("2")).toBe(true);
    expect(isValidCost("100")).toBe(true);
  });

  it("rejects empty string", () => {
    expect(isValidCost("")).toBe(false);
  });

  it("rejects non-numeric strings", () => {
    expect(isValidCost("abc")).toBe(false);
    expect(isValidCost("$1.00")).toBe(false);
  });

  it("rejects negative values", () => {
    expect(isValidCost("-0.001")).toBe(false);
    expect(isValidCost("-1")).toBe(false);
  });

  it("rejects NaN and Infinity", () => {
    expect(isValidCost("NaN")).toBe(false);
    expect(isValidCost("Infinity")).toBe(false);
  });
});

/* -------------------------------------------------------------------------- */
/* Unpriced alias detection                                                   */
/* -------------------------------------------------------------------------- */

interface MockEvent {
  alias: string;
}

function detectUnpricedAliases(
  events: MockEvent[],
  pricedAliases: Set<string>,
): string[] {
  const seen = new Set<string>();
  const unpriced: string[] = [];
  for (const ev of events) {
    if (!pricedAliases.has(ev.alias) && !seen.has(ev.alias)) {
      seen.add(ev.alias);
      unpriced.push(ev.alias);
    }
  }
  return unpriced;
}

describe("detectUnpricedAliases", () => {
  it("returns empty array when all aliases are priced", () => {
    const events: MockEvent[] = [
      { alias: "chat_cheap" },
      { alias: "chat_reasoning" },
    ];
    const priced = new Set(["chat_cheap", "chat_reasoning"]);
    expect(detectUnpricedAliases(events, priced)).toEqual([]);
  });

  it("returns aliases that have events but no price row", () => {
    const events: MockEvent[] = [
      { alias: "chat_cheap" },
      { alias: "new_model" },
    ];
    const priced = new Set(["chat_cheap"]);
    expect(detectUnpricedAliases(events, priced)).toEqual(["new_model"]);
  });

  it("deduplicates repeated unpriced aliases", () => {
    const events: MockEvent[] = [
      { alias: "unpriced" },
      { alias: "unpriced" },
      { alias: "unpriced" },
    ];
    const priced = new Set<string>();
    expect(detectUnpricedAliases(events, priced)).toEqual(["unpriced"]);
  });

  it("returns multiple distinct unpriced aliases in insertion order", () => {
    const events: MockEvent[] = [
      { alias: "a" },
      { alias: "b" },
      { alias: "a" },
      { alias: "c" },
    ];
    const priced = new Set<string>();
    expect(detectUnpricedAliases(events, priced)).toEqual(["a", "b", "c"]);
  });

  it("handles empty events array", () => {
    expect(detectUnpricedAliases([], new Set(["chat_cheap"]))).toEqual([]);
  });
});

/* -------------------------------------------------------------------------- */
/* Price form — effective_from / effective_until display                      */
/* -------------------------------------------------------------------------- */

describe("effective date display slicing", () => {
  it("truncates ISO datetime to date-only for display", () => {
    const date = "2026-01-15T00:00:00Z";
    expect(date.slice(0, 10)).toBe("2026-01-15");
  });

  it("handles date-only strings unchanged", () => {
    const date = "2026-01-15";
    expect(date.slice(0, 10)).toBe("2026-01-15");
  });
});

/* -------------------------------------------------------------------------- */
/* formatUsd used in pricing table cells                                      */
/* -------------------------------------------------------------------------- */

describe("formatUsd in pricing table", () => {
  it("formats prompt cost per 1k correctly (4dp for sub-cent)", () => {
    expect(formatUsd("0.0015")).toBe("$0.0015");
  });

  it("formats higher costs with 2dp", () => {
    expect(formatUsd("0.02")).toBe("$0.02");
  });

  it("shows $— for malformed string", () => {
    expect(formatUsd("invalid")).toBe("$—");
  });
});

/* -------------------------------------------------------------------------- */
/* priceToForm mapping                                                        */
/* -------------------------------------------------------------------------- */

interface PriceFormState {
  alias: string;
  prompt_cost_per_1k: string;
  completion_cost_per_1k: string;
  effective_from: string;
  effective_until: string;
  notes: string;
}

function priceToForm(p: AiOpsPrice): PriceFormState {
  return {
    alias: p.alias,
    prompt_cost_per_1k: p.prompt_cost_per_1k,
    completion_cost_per_1k: p.completion_cost_per_1k,
    effective_from: p.effective_from.slice(0, 10),
    effective_until: p.effective_until ? p.effective_until.slice(0, 10) : "",
    notes: p.notes ?? "",
  };
}

describe("priceToForm", () => {
  const sample: AiOpsPrice = {
    id: "price-1",
    alias: "chat_cheap",
    prompt_cost_per_1k: "0.0015",
    completion_cost_per_1k: "0.0020",
    effective_from: "2026-01-01T00:00:00Z",
    effective_until: "2026-12-31T23:59:59Z",
    notes: "Test note",
    created_at: "2026-01-01T00:00:00Z",
    updated_at: null,
  };

  it("maps alias correctly", () => {
    expect(priceToForm(sample).alias).toBe("chat_cheap");
  });

  it("truncates effective_from to date-only", () => {
    expect(priceToForm(sample).effective_from).toBe("2026-01-01");
  });

  it("truncates effective_until to date-only", () => {
    expect(priceToForm(sample).effective_until).toBe("2026-12-31");
  });

  it("maps effective_until to empty string when null", () => {
    const noUntil: AiOpsPrice = { ...sample, effective_until: null };
    expect(priceToForm(noUntil).effective_until).toBe("");
  });

  it("maps notes to empty string when null", () => {
    const noNotes: AiOpsPrice = { ...sample, notes: null };
    expect(priceToForm(noNotes).notes).toBe("");
  });

  it("preserves cost strings", () => {
    const form = priceToForm(sample);
    expect(form.prompt_cost_per_1k).toBe("0.0015");
    expect(form.completion_cost_per_1k).toBe("0.0020");
  });
});
