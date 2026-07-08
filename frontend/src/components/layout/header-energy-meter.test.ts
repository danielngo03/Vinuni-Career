/**
 * HeaderEnergyMeter visibility + tone-derivation tests.
 *
 * The vitest environment here is `node` (no DOM), so — as with every other test
 * in this repo (see `admin-guard.test.tsx`) — we test the component's pure
 * decision logic directly instead of rendering the JSX tree:
 *
 *  1. `headerEnergyMeterVisible` is the gate that makes the meter a student-only
 *     header affordance. Contract under test: it renders iff
 *       status === "authenticated" && persona resolves to "student"
 *     i.e. an authenticated student sees the header meter; a guest (and a
 *     partner/university user) does not. This is exactly the "student header
 *     shows the meter and a guest does not" contract.
 *  2. `deriveEnergyMeterState` turns the masked `AiEnergyUsage` payload into the
 *     ok/warn/block tone + rounded remaining %. No token/USD/provider value is
 *     ever derived — only the masked percentage and coarse state.
 */
import { describe, it, expect } from "vitest";
import type { AiEnergyUsage } from "@/lib/api/ai-assistant";
import {
  deriveEnergyMeterState,
  headerEnergyMeterVisible,
  ENERGY_WARN_REMAINING_PCT,
} from "./ai-energy-meter";

/** A healthy, non-blocked personal-budget usage payload. */
function makeUsage(overrides: Partial<AiEnergyUsage> = {}): AiEnergyUsage {
  return {
    scope: "user",
    energy_pct: 82,
    weekly: { used: 90, allowance: 500, wallet: 0, capacity: 500 },
    session_3h: { used: 2, soft_cap: 20, over_soft_cap: false },
    blocked: false,
    blocked_reason: null,
    warning: false,
    warning_reason: null,
    week_reset: "2026-07-13T00:00:00Z",
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// Visibility — student sees the header meter, guest does not
// ---------------------------------------------------------------------------

describe("headerEnergyMeterVisible", () => {
  it("shows the meter for an authenticated student", () => {
    expect(headerEnergyMeterVisible("authenticated", "student")).toBe(true);
  });

  it("defaults a null/undefined authenticated persona to student (marketplace fallback)", () => {
    expect(headerEnergyMeterVisible("authenticated", null)).toBe(true);
    expect(headerEnergyMeterVisible("authenticated", undefined)).toBe(true);
  });

  it("hides the meter from a guest", () => {
    expect(headerEnergyMeterVisible("guest", null)).toBe(false);
    expect(headerEnergyMeterVisible("guest", "student")).toBe(false);
  });

  it("hides the meter while auth is still unknown (no flash)", () => {
    expect(headerEnergyMeterVisible("unknown", null)).toBe(false);
  });

  it("hides the meter from authenticated partner / university users", () => {
    expect(headerEnergyMeterVisible("authenticated", "partner")).toBe(false);
    expect(headerEnergyMeterVisible("authenticated", "university")).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// Tone derivation — masked % → ok / warn / block
// ---------------------------------------------------------------------------

describe("deriveEnergyMeterState", () => {
  it("is OK (green) with plenty of energy remaining", () => {
    const s = deriveEnergyMeterState(makeUsage({ energy_pct: 82 }));
    expect(s.tone).toBe("ok");
    expect(s.pct).toBe(82);
    expect(s.fillPct).toBe(82);
    expect(s.isOrg).toBe(false);
  });

  it("warns (amber) at ~80% used even without a backend warning flag", () => {
    // 20% remaining == 80% used → warn threshold.
    const s = deriveEnergyMeterState(
      makeUsage({ energy_pct: ENERGY_WARN_REMAINING_PCT, warning: false }),
    );
    expect(s.tone).toBe("warn");
    expect(s.pct).toBe(ENERGY_WARN_REMAINING_PCT);
  });

  it("warns (amber) when the backend raises its own soft-warning flag", () => {
    const s = deriveEnergyMeterState(
      makeUsage({ energy_pct: 55, warning: true, warning_reason: "AI_SESSION_BURST" }),
    );
    expect(s.tone).toBe("warn");
  });

  it("blocks (red) when weekly energy is exhausted, overriding warn/ok", () => {
    const s = deriveEnergyMeterState(
      makeUsage({
        energy_pct: 0,
        blocked: true,
        blocked_reason: "AI_WEEKLY_ENERGY_EXCEEDED",
        warning: true,
      }),
    );
    expect(s.tone).toBe("block");
    expect(s.pct).toBe(0);
  });

  it("flags an org-pool scope and passes through the 3h burst soft cap", () => {
    const s = deriveEnergyMeterState(
      makeUsage({
        scope: "org",
        session_3h: { used: 25, soft_cap: 20, over_soft_cap: true },
      }),
    );
    expect(s.isOrg).toBe(true);
    expect(s.overSoftCap).toBe(true);
  });

  it("rounds the display % and clamps the fill fraction to 0..100", () => {
    expect(deriveEnergyMeterState(makeUsage({ energy_pct: 82.6 })).pct).toBe(83);
    expect(deriveEnergyMeterState(makeUsage({ energy_pct: 140 })).fillPct).toBe(100);
    expect(deriveEnergyMeterState(makeUsage({ energy_pct: -5 })).fillPct).toBe(0);
  });
});
