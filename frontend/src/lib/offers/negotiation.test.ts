/**
 * Offer negotiation gating — pure logic tests (vitest env `node`, no DOM).
 *
 * Load-bearing contract: the metered negotiation request must fire ONLY after
 * explicit confirmation. `shouldRunNegotiation` is the exact gate the drawer
 * uses, so "no fetch before confirm" is a provable, tested property.
 */
import { describe, it, expect } from "vitest";
import type { OfferBenchmark } from "@/lib/api/applications/offers";
import { shouldRunNegotiation, marketPositionTone } from "@/lib/offers/negotiation";

describe("shouldRunNegotiation — confirmation gate", () => {
  it("does NOT run before the student confirms", () => {
    expect(shouldRunNegotiation(false)).toBe(false);
  });

  it("runs only once the student has confirmed", () => {
    expect(shouldRunNegotiation(true)).toBe(true);
  });
});

describe("marketPositionTone", () => {
  const found = (
    pos: OfferBenchmark["position_vs_market"],
  ): OfferBenchmark => ({
    found: true,
    market_band: "10–20",
    position_vs_market: pos,
  });

  it("maps a below-market verdict to the attention tone", () => {
    expect(marketPositionTone(found("below_market"))).toBe("below");
  });

  it("maps within/above verdicts to their tones", () => {
    expect(marketPositionTone(found("within_market"))).toBe("within");
    expect(marketPositionTone(found("above_market"))).toBe("above");
  });

  it("is unknown when the role is not in the benchmark", () => {
    expect(marketPositionTone({ found: false })).toBe("unknown");
    expect(marketPositionTone(null)).toBe("unknown");
    expect(marketPositionTone(undefined)).toBe("unknown");
  });

  it("is unknown when comp is undisclosed (no position asserted)", () => {
    expect(marketPositionTone(found(null))).toBe("unknown");
  });
});
