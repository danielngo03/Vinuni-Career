import { describe, expect, it } from "vitest";
import { computeBarGeometry } from "@/components/ui/bar-series-math";
import { computeSparklinePoints } from "@/components/ui/sparkline-math";

// ---------------------------------------------------------------------------
// computeBarGeometry
// ---------------------------------------------------------------------------

describe("computeBarGeometry", () => {
  it("returns 2 entries for 2-item input", () => {
    const result = computeBarGeometry([
      { label: "a", value: 2 },
      { label: "b", value: 4 },
    ]);
    expect(result).toHaveLength(2);
  });

  it("max-value bar has heightPct === 100", () => {
    const result = computeBarGeometry([
      { label: "a", value: 2 },
      { label: "b", value: 4 },
    ]);
    const maxBar = result.find((r) => r.label === "b");
    expect(maxBar?.heightPct).toBe(100);
  });

  it("half-value bar has heightPct === 50", () => {
    const result = computeBarGeometry([
      { label: "a", value: 2 },
      { label: "b", value: 4 },
    ]);
    const halfBar = result.find((r) => r.label === "a");
    expect(halfBar?.heightPct).toBe(50);
  });

  it("returns [] for empty input (no crash, no NaN)", () => {
    const result = computeBarGeometry([]);
    expect(result).toEqual([]);
  });

  it("flags only the max-value entry as isMax", () => {
    const result = computeBarGeometry([
      { label: "x", value: 10 },
      { label: "y", value: 5 },
      { label: "z", value: 10 },
    ]);
    const maxEntries = result.filter((r) => r.isMax);
    // Both x and z have value 10 — both should be flagged
    expect(maxEntries).toHaveLength(2);
  });

  it("does not produce NaN when all values are zero", () => {
    const result = computeBarGeometry([
      { label: "a", value: 0 },
      { label: "b", value: 0 },
    ]);
    result.forEach((r) => {
      expect(Number.isNaN(r.heightPct)).toBe(false);
    });
  });

  it("respects the minHeightPct floor", () => {
    const result = computeBarGeometry(
      [
        { label: "tiny", value: 1 },
        { label: "big", value: 1000 },
      ],
      { minHeightPct: 5 },
    );
    const tinyBar = result.find((r) => r.label === "tiny");
    expect(tinyBar?.heightPct).toBeGreaterThanOrEqual(5);
  });

  it("preserves label and value on each entry", () => {
    const result = computeBarGeometry([{ label: "jan", value: 42 }]);
    expect(result[0]?.label).toBe("jan");
    expect(result[0]?.value).toBe(42);
  });
});

// ---------------------------------------------------------------------------
// computeSparklinePoints
// ---------------------------------------------------------------------------

describe("computeSparklinePoints", () => {
  const W = 120;
  const H = 32;

  it("returns [] for empty data (no crash)", () => {
    const result = computeSparklinePoints([], W, H);
    expect(result).toEqual([]);
  });

  it("returns 2 points for a single-value array (no crash)", () => {
    const result = computeSparklinePoints([7], W, H);
    expect(result).toHaveLength(2);
  });

  it("first point x is 0, last point x is width", () => {
    const result = computeSparklinePoints([1, 2, 3], W, H);
    expect(result[0]?.x).toBe(0);
    expect(result[result.length - 1]?.x).toBe(W);
  });

  it("min-value point has y === height (bottom), max-value has y === 0 (top)", () => {
    const result = computeSparklinePoints([0, 10], W, H);
    // index 0 = value 0 (min) → y should be H (bottom)
    expect(result[0]?.y).toBe(H);
    // index 1 = value 10 (max) → y should be 0 (top)
    expect(result[1]?.y).toBe(0);
  });

  it("produces no NaN coordinates", () => {
    const result = computeSparklinePoints([5, 5, 5], W, H);
    result.forEach((p) => {
      expect(Number.isNaN(p.x)).toBe(false);
      expect(Number.isNaN(p.y)).toBe(false);
    });
  });

  it("clamps NaN values to 0 without crashing", () => {
    const result = computeSparklinePoints([NaN, 5], W, H);
    expect(result).toHaveLength(2);
    result.forEach((p) => {
      expect(Number.isNaN(p.x)).toBe(false);
      expect(Number.isNaN(p.y)).toBe(false);
    });
  });
});
