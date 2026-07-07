/**
 * AI Pricing screen — pure unit tests.
 *
 * The vitest environment is `node` (no DOM), so we test the pure helper
 * functions and pure logic that drive the pricing table and form validation.
 *
 * Contract aligned to the real backend fields:
 *   provider, model, input_usd_per_1k, output_usd_per_1k, active, updated_at
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
/* priceToForm mapping — real backend fields                                  */
/* -------------------------------------------------------------------------- */

interface PriceFormState {
  provider: string;
  model: string;
  input_usd_per_1k: string;
  output_usd_per_1k: string;
  active: boolean;
}

function priceToForm(p: AiOpsPrice): PriceFormState {
  return {
    provider: p.provider,
    model: p.model,
    input_usd_per_1k: String(p.input_usd_per_1k),
    output_usd_per_1k: String(p.output_usd_per_1k),
    active: p.active,
  };
}

describe("priceToForm — real backend contract", () => {
  const sample: AiOpsPrice = {
    id: "price-1",
    provider: "openrouter",
    model: "deepseek/deepseek-v3",
    input_usd_per_1k: 0.0015,
    output_usd_per_1k: 0.002,
    active: true,
    updated_by: null,
    updated_at: "2026-01-15T00:00:00Z",
  };

  it("maps provider correctly", () => {
    expect(priceToForm(sample).provider).toBe("openrouter");
  });

  it("maps model correctly", () => {
    expect(priceToForm(sample).model).toBe("deepseek/deepseek-v3");
  });

  it("serialises input_usd_per_1k to string for the form input", () => {
    expect(priceToForm(sample).input_usd_per_1k).toBe("0.0015");
  });

  it("serialises output_usd_per_1k to string for the form input", () => {
    expect(priceToForm(sample).output_usd_per_1k).toBe("0.002");
  });

  it("preserves active flag", () => {
    expect(priceToForm(sample).active).toBe(true);
    const inactive: AiOpsPrice = { ...sample, active: false };
    expect(priceToForm(inactive).active).toBe(false);
  });
});

/* -------------------------------------------------------------------------- */
/* updated_at display slicing                                                  */
/* -------------------------------------------------------------------------- */

describe("updated_at display slicing", () => {
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
  it("formats input_usd_per_1k with 4dp for sub-cent amounts (number input)", () => {
    expect(formatUsd(0.0015)).toBe("$0.0015");
  });

  it("formats output_usd_per_1k with 4dp for sub-cent amounts (number input)", () => {
    expect(formatUsd(0.002)).toBe("$0.0020");
  });

  it("formats higher costs with 2dp", () => {
    expect(formatUsd(0.02)).toBe("$0.02");
  });

  it("shows $— for NaN", () => {
    expect(formatUsd(NaN)).toBe("$—");
  });
});
