/**
 * Energy wallet view — pure logic tests (vitest env `node`, no DOM).
 *
 * Load-bearing contract: the wallet panel is MASKED. It derives only a
 * percentage, a coarse ok/warn/block tone, and a two-state wallet BUCKET — never
 * a raw wallet credit count, token, USD, or provider signal. These tests assert
 * the bucket is coarse (an enum, not the underlying number) and the view exposes
 * no raw wallet figure.
 */
import { describe, it, expect } from "vitest";
import type { AiEnergyUsage } from "@/lib/api/ai-assistant";
import { deriveWalletBucket, energyWalletView } from "@/lib/billing/energy-wallet";

function usage(overrides: Partial<AiEnergyUsage> = {}): AiEnergyUsage {
  return {
    scope: "user",
    energy_pct: 60,
    weekly: { used: 200, allowance: 500, wallet: 0, capacity: 500 },
    session_3h: { used: 2, soft_cap: 20, over_soft_cap: false },
    blocked: false,
    blocked_reason: null,
    warning: false,
    warning_reason: null,
    week_reset: "2026-07-13T00:00:00Z",
    ...overrides,
  };
}

describe("deriveWalletBucket — coarse, never a raw number", () => {
  it("is 'none' with an empty top-up reserve", () => {
    expect(deriveWalletBucket(usage({ weekly: { used: 0, allowance: 500, wallet: 0, capacity: 500 } }))).toBe("none");
  });

  it("is 'reserve' with any top-up left — the exact count is never surfaced", () => {
    const big = deriveWalletBucket(usage({ weekly: { used: 0, allowance: 500, wallet: 999, capacity: 1499 } }));
    const small = deriveWalletBucket(usage({ weekly: { used: 0, allowance: 500, wallet: 1, capacity: 501 } }));
    // Both collapse to the same coarse bucket regardless of magnitude.
    expect(big).toBe("reserve");
    expect(small).toBe("reserve");
    expect(big).toBe(small);
  });
});

describe("energyWalletView — masked display shape", () => {
  it("exposes only masked fields (no raw wallet/token/USD leaks)", () => {
    const view = energyWalletView(usage({ energy_pct: 60, weekly: { used: 200, allowance: 500, wallet: 40, capacity: 540 } }));
    expect(view.pct).toBe(60);
    expect(view.walletBucket).toBe("reserve");
    // The view keys are strictly the masked set — no `wallet`/`used`/`allowance`.
    expect(Object.keys(view).sort()).toEqual(
      ["blocked", "fillPct", "isOrg", "pct", "tone", "walletBucket", "warning"].sort(),
    );
  });

  it("rounds + clamps the percentage and mirrors the shared tone derivation", () => {
    expect(energyWalletView(usage({ energy_pct: 59.6 })).pct).toBe(60);
    expect(energyWalletView(usage({ energy_pct: 140 })).fillPct).toBe(100);
    expect(energyWalletView(usage({ energy_pct: 82 })).tone).toBe("ok");
    expect(energyWalletView(usage({ energy_pct: 15 })).tone).toBe("warn");
  });

  it("reports the block tone when weekly energy is exhausted", () => {
    const view = energyWalletView(
      usage({ energy_pct: 0, blocked: true, blocked_reason: "AI_WEEKLY_ENERGY_EXCEEDED" }),
    );
    expect(view.blocked).toBe(true);
    expect(view.tone).toBe("block");
  });

  it("flags an org-pool scope", () => {
    expect(energyWalletView(usage({ scope: "org" })).isOrg).toBe(true);
  });
});
