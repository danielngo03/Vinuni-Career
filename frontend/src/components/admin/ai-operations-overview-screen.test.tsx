/**
 * AI Operations Overview — pure helper unit tests.
 *
 * The vitest environment is `node` (no DOM), so we test pure functions only:
 * `budgetTone`, `budgetBurnPct`, `formatUsd`, `formatLatency`, `formatErrorRate`.
 *
 * These helpers drive the metric tile tonal badges and formatted values shown
 * to operators. Testing them at the threshold boundaries gives confidence that
 * the teal/amber/red budget-burn logic is correct before any render path.
 */
import { describe, it, expect } from "vitest";
import {
  budgetTone,
  budgetBurnPct,
  formatUsd,
  formatLatency,
  formatErrorRate,
} from "./ai-ops-helpers";

/* -------------------------------------------------------------------------- */
/* budgetTone — teal / amber / red thresholds                                 */
/* -------------------------------------------------------------------------- */

describe("budgetTone", () => {
  it("returns teal when spend is 0", () => {
    expect(budgetTone(0, 100)).toBe("teal");
    expect(budgetTone("0", "100")).toBe("teal");
  });

  it("returns teal when burn is exactly 69.99%", () => {
    expect(budgetTone(69.99, 100)).toBe("teal");
  });

  it("returns amber at exactly 70%", () => {
    expect(budgetTone(70, 100)).toBe("amber");
    expect(budgetTone("70", "100")).toBe("amber");
  });

  it("returns amber at 89.99%", () => {
    expect(budgetTone(89.99, 100)).toBe("amber");
  });

  it("returns amber at exactly 90%", () => {
    expect(budgetTone(90, 100)).toBe("amber");
  });

  it("returns red above 90%", () => {
    expect(budgetTone(90.01, 100)).toBe("red");
    expect(budgetTone("91", "100")).toBe("red");
  });

  it("returns red at exactly 100%", () => {
    expect(budgetTone(100, 100)).toBe("red");
  });

  it("returns red when over budget (>100%)", () => {
    expect(budgetTone(150, 100)).toBe("red");
  });

  it("returns teal when budget is 0 (guards division by zero)", () => {
    expect(budgetTone(10, 0)).toBe("teal");
    expect(budgetTone("10", "0")).toBe("teal");
  });

  it("returns teal for NaN / invalid strings", () => {
    expect(budgetTone("abc", "100")).toBe("teal");
    expect(budgetTone(NaN, 100)).toBe("teal");
  });

  it("works with string inputs matching API shape (decimal USD)", () => {
    // API returns cost_usd as string decimal
    expect(budgetTone("0.4500", "1.0000")).toBe("teal");   // 45%
    expect(budgetTone("0.7200", "1.0000")).toBe("amber");  // 72%
    expect(budgetTone("0.9500", "1.0000")).toBe("red");    // 95%
  });
});

/* -------------------------------------------------------------------------- */
/* budgetBurnPct                                                               */
/* -------------------------------------------------------------------------- */

describe("budgetBurnPct", () => {
  it("returns 0 when spend is 0", () => {
    expect(budgetBurnPct(0, 100)).toBe(0);
  });

  it("returns 50 for 50% spend", () => {
    expect(budgetBurnPct(50, 100)).toBe(50);
  });

  it("caps at 999", () => {
    expect(budgetBurnPct(10000, 100)).toBe(999);
  });

  it("returns 0 for zero budget", () => {
    expect(budgetBurnPct(10, 0)).toBe(0);
  });

  it("rounds correctly", () => {
    expect(budgetBurnPct(1, 3)).toBe(33);
    expect(budgetBurnPct(2, 3)).toBe(67);
  });
});

/* -------------------------------------------------------------------------- */
/* formatUsd                                                                   */
/* -------------------------------------------------------------------------- */

describe("formatUsd", () => {
  it("formats zero", () => {
    expect(formatUsd(0)).toBe("$0.00");
    expect(formatUsd("0")).toBe("$0.00");
  });

  it("formats 2dp for values >= $0.01", () => {
    expect(formatUsd(1.5)).toBe("$1.50");
    expect(formatUsd("0.01")).toBe("$0.01");
  });

  it("formats 4dp for micro-amounts under $0.01", () => {
    expect(formatUsd(0.001)).toBe("$0.0010");
    expect(formatUsd("0.0045")).toBe("$0.0045");
  });

  it("returns $— for NaN", () => {
    expect(formatUsd("abc")).toBe("$—");
    expect(formatUsd(NaN)).toBe("$—");
  });
});

/* -------------------------------------------------------------------------- */
/* formatLatency                                                               */
/* -------------------------------------------------------------------------- */

describe("formatLatency", () => {
  it("formats sub-second as ms", () => {
    expect(formatLatency(250)).toBe("250ms");
    expect(formatLatency(999)).toBe("999ms");
  });

  it("formats >= 1000ms as seconds", () => {
    expect(formatLatency(1000)).toBe("1.0s");
    expect(formatLatency(2500)).toBe("2.5s");
  });

  it("returns — for negative or non-finite", () => {
    expect(formatLatency(-1)).toBe("—");
    expect(formatLatency(NaN)).toBe("—");
    expect(formatLatency(Infinity)).toBe("—");
  });

  it("rounds sub-second to nearest integer ms", () => {
    expect(formatLatency(123.7)).toBe("124ms");
  });
});

/* -------------------------------------------------------------------------- */
/* formatErrorRate                                                             */
/* -------------------------------------------------------------------------- */

describe("formatErrorRate", () => {
  it("formats 0 as 0.00%", () => {
    expect(formatErrorRate(0)).toBe("0.00%");
  });

  it("formats 0.05 as 5.00%", () => {
    expect(formatErrorRate(0.05)).toBe("5.00%");
  });

  it("formats very small non-zero as <0.01%", () => {
    expect(formatErrorRate(0.00001)).toBe("<0.01%");
  });

  it("formats 1.0 (100% error) correctly", () => {
    expect(formatErrorRate(1.0)).toBe("100.00%");
  });

  it("returns — for NaN", () => {
    expect(formatErrorRate(NaN)).toBe("—");
  });
});
