import { describe, expect, it } from "vitest";
import {
  clampPct,
  energyTone,
  formatUnits,
  TOPUP_STATUS_TONE,
} from "@/lib/ai-energy/format";

describe("energyTone", () => {
  it("returns normal for a healthy pool", () => {
    expect(energyTone({ blocked: false, warning: false })).toBe("normal");
    expect(energyTone({})).toBe("normal");
  });

  it("returns warning when only warning is set", () => {
    expect(energyTone({ warning: true })).toBe("warning");
  });

  it("prioritises critical over warning when blocked", () => {
    expect(energyTone({ blocked: true, warning: true })).toBe("critical");
  });
});

describe("clampPct", () => {
  it("clamps below 0 and above 100", () => {
    expect(clampPct(-25)).toBe(0);
    expect(clampPct(140)).toBe(100);
  });

  it("passes through in-range values", () => {
    expect(clampPct(42)).toBe(42);
  });

  it("treats null/NaN as 0", () => {
    expect(clampPct(null)).toBe(0);
    expect(clampPct(Number.NaN)).toBe(0);
  });
});

describe("formatUnits", () => {
  it("groups thousands per locale", () => {
    expect(formatUnits(1200, "en")).toBe("1,200");
    expect(formatUnits(1200, "vi")).toBe("1.200");
  });

  it("renders a dash for missing values", () => {
    expect(formatUnits(null, "en")).toBe("—");
    expect(formatUnits(Number.NaN, "vi")).toBe("—");
  });
});

describe("TOPUP_STATUS_TONE", () => {
  it("maps every top-up status to a badge tone", () => {
    expect(TOPUP_STATUS_TONE.pending).toBe("pending");
    expect(TOPUP_STATUS_TONE.paid).toBe("active");
    expect(TOPUP_STATUS_TONE.cancelled).toBe("rejected");
  });
});
