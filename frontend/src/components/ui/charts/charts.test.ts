import { describe, expect, it } from "vitest";

/**
 * Unit tests for chart pure helpers.
 * Import ONLY from .ts files — the node test env cannot parse JSX from .tsx.
 */

// Pure helpers from chart-theme
import {
  seriesColor,
  toneColor,
  buildMonochromeScale,
  buildSeverityScale,
  hexToRgb,
  lerpHex,
  CHART_INK,
  CHART_TEAL,
  CHART_AMBER,
  CHART_RED,
} from "./chart-theme";

// Pure helpers from chart-helpers
import {
  formatTick,
  donutTotal,
  sliceColor,
  buildColorScale,
} from "./chart-helpers";

// Type imports (compile-time only — no runtime import of .tsx files)
import type { FormatKind, DonutSliceData } from "./chart-helpers";

/**
 * Series/slice resolvers now return theme-aware color TOKENS: a literal 6-digit
 * hex (explicit overrides, interpolated heatmap fills) OR a `var(--chart-*)`
 * custom property that resolves per [data-theme]. This matcher accepts either.
 */
const COLOR_TOKEN = /^(#[0-9a-f]{6}|var\(--[a-z0-9-]+\))$/i;

// ── chart-theme: seriesColor ──────────────────────────────────────────────────

describe("seriesColor", () => {
  it("index 0 returns ink", () => {
    expect(seriesColor(0)).toBe(CHART_INK);
  });

  it("index 1 returns first gray (not ink)", () => {
    const color = seriesColor(1);
    expect(color).not.toBe(CHART_INK);
    expect(color).toMatch(COLOR_TOKEN);
  });

  it("high index clamps to last gray — no crash, no undefined", () => {
    const color = seriesColor(100);
    expect(color).toMatch(COLOR_TOKEN);
  });

  it("all indexes 0–7 return valid color tokens", () => {
    for (let i = 0; i <= 7; i++) {
      expect(seriesColor(i)).toMatch(COLOR_TOKEN);
    }
  });
});

// ── chart-theme: toneColor ────────────────────────────────────────────────────

describe("toneColor", () => {
  it("success → teal", () => {
    expect(toneColor("success")).toBe(CHART_TEAL);
  });

  it("warning → amber", () => {
    expect(toneColor("warning")).toBe(CHART_AMBER);
  });

  it("error → red", () => {
    expect(toneColor("error")).toBe(CHART_RED);
  });

  it("undefined → fallback (ink by default)", () => {
    expect(toneColor(undefined)).toBe(CHART_INK);
  });

  it("neutral → fallback (ink by default)", () => {
    expect(toneColor("neutral")).toBe(CHART_INK);
  });

  it("custom fallback is respected", () => {
    expect(toneColor(undefined, "#ff0000")).toBe("#ff0000");
  });
});

// ── chart-theme: buildMonochromeScale ─────────────────────────────────────────

describe("buildMonochromeScale", () => {
  it("returns correct number of steps", () => {
    expect(buildMonochromeScale(5)).toHaveLength(5);
  });

  it("first step is near-white (high R value)", () => {
    const first = buildMonochromeScale(2)[0] ?? "";
    const [r] = hexToRgb(first);
    expect(r).toBeGreaterThan(200);
  });

  it("last step is near-ink (low R value)", () => {
    const scale = buildMonochromeScale(2);
    const last = scale[scale.length - 1] ?? "";
    const [r] = hexToRgb(last);
    expect(r).toBeLessThan(50);
  });

  it("single step returns 1 color — no crash", () => {
    expect(buildMonochromeScale(1)).toHaveLength(1);
  });

  it("all entries are valid hex colors", () => {
    buildMonochromeScale(8).forEach((c) => {
      expect(c).toMatch(/^#[0-9a-f]{6}$/i);
    });
  });
});

// ── chart-theme: buildSeverityScale ──────────────────────────────────────────

describe("buildSeverityScale", () => {
  it("returns correct number of steps", () => {
    expect(buildSeverityScale(5)).toHaveLength(5);
  });

  it("returns [] for 0 steps — no crash", () => {
    expect(buildSeverityScale(0)).toEqual([]);
  });

  it("single step returns [amber]", () => {
    expect(buildSeverityScale(1)).toEqual([CHART_AMBER]);
  });

  it("all entries are valid hex colors", () => {
    buildSeverityScale(7).forEach((c) => {
      expect(c).toMatch(/^#[0-9a-f]{6}$/i);
    });
  });
});

// ── chart-theme: hexToRgb ─────────────────────────────────────────────────────

describe("hexToRgb", () => {
  it("parses #ffffff as [255,255,255]", () => {
    expect(hexToRgb("#ffffff")).toEqual([255, 255, 255]);
  });

  it("parses #000000 as [0,0,0]", () => {
    expect(hexToRgb("#000000")).toEqual([0, 0, 0]);
  });

  it("parses ink #171717 as [23,23,23]", () => {
    expect(hexToRgb("#171717")).toEqual([23, 23, 23]);
  });
});

// ── chart-theme: lerpHex ──────────────────────────────────────────────────────

describe("lerpHex", () => {
  it("t=0 returns first color", () => {
    expect(lerpHex("#000000", "#ffffff", 0)).toBe("#000000");
  });

  it("t=1 returns second color", () => {
    expect(lerpHex("#000000", "#ffffff", 1)).toBe("#ffffff");
  });

  it("t=0.5 of #000000→#ffffff is mid-gray (R ≈ 127–128)", () => {
    const mid = lerpHex("#000000", "#ffffff", 0.5);
    const [r] = hexToRgb(mid);
    expect(r).toBeGreaterThanOrEqual(120);
    expect(r).toBeLessThanOrEqual(135);
  });

  it("output is valid hex", () => {
    expect(lerpHex("#171717", "#d97706", 0.5)).toMatch(/^#[0-9a-f]{6}$/i);
  });
});

// ── chart-helpers: formatTick ─────────────────────────────────────────────────

describe("formatTick", () => {
  it("default kind is number — compact notation", () => {
    // Vietnamese locale uses comma as thousands separator; compact gives "1,2K" or "1.2K"
    const result = formatTick(1200, "number");
    expect(result).toBeTruthy();
    expect(typeof result).toBe("string");
  });

  it("ms format: shows ms for values under 1000", () => {
    expect(formatTick(500, "ms")).toBe("500ms");
  });

  it("ms format: shows seconds for values >= 1000", () => {
    expect(formatTick(1500, "ms")).toBe("1.5s");
  });

  it("ms format: exactly 1000 = 1.0s", () => {
    expect(formatTick(1000, "ms")).toBe("1.0s");
  });

  it("percent format includes %", () => {
    const result = formatTick(45.678, "percent");
    expect(result).toMatch(/%/);
    expect(result).toContain("45.7");
  });

  it("non-finite (NaN) returns em-dash", () => {
    expect(formatTick(NaN, "number")).toBe("—");
  });

  it("non-finite (Infinity) returns em-dash", () => {
    expect(formatTick(Infinity, "ms")).toBe("—");
  });

  it("zero ms → 0ms", () => {
    expect(formatTick(0, "ms")).toBe("0ms");
  });

  it("zero percent → 0.0%", () => {
    expect(formatTick(0, "percent")).toBe("0.0%");
  });

  it("FormatKind type covers all expected values", () => {
    // Type-level check — ensures FormatKind includes these strings
    const kinds: FormatKind[] = ["number", "currency", "ms", "percent"];
    expect(kinds).toHaveLength(4);
  });
});

// ── chart-helpers: donutTotal ─────────────────────────────────────────────────

describe("donutTotal", () => {
  it("sums values correctly", () => {
    const data: DonutSliceData[] = [
      { label: "a", value: 10 },
      { label: "b", value: 20 },
      { label: "c", value: 5 },
    ];
    expect(donutTotal(data)).toBe(35);
  });

  it("returns 0 for empty array — no crash", () => {
    expect(donutTotal([])).toBe(0);
  });

  it("ignores NaN values without crash", () => {
    expect(donutTotal([
      { label: "a", value: NaN },
      { label: "b", value: 10 },
    ])).toBe(10);
  });

  it("handles all-zero input", () => {
    expect(donutTotal([
      { label: "a", value: 0 },
      { label: "b", value: 0 },
    ])).toBe(0);
  });

  it("single item", () => {
    expect(donutTotal([{ label: "x", value: 42 }])).toBe(42);
  });
});

// ── chart-helpers: sliceColor ─────────────────────────────────────────────────

describe("sliceColor", () => {
  it("index 0 with no override returns ink", () => {
    expect(sliceColor({ label: "x", value: 1 }, 0)).toBe(CHART_INK);
  });

  it("explicit color takes priority over tone and ramp", () => {
    expect(
      sliceColor({ label: "x", value: 1, color: "#ff0000", tone: "success" }, 0),
    ).toBe("#ff0000");
  });

  it("tone takes priority over ramp when no explicit color", () => {
    expect(
      sliceColor({ label: "x", value: 1, tone: "success" }, 0),
    ).toBe(CHART_TEAL);
  });

  it("warning tone → amber", () => {
    expect(sliceColor({ label: "x", value: 1, tone: "warning" }, 2)).toBe(CHART_AMBER);
  });

  it("error tone → brand red", () => {
    expect(sliceColor({ label: "x", value: 1, tone: "error" }, 2)).toBe(CHART_RED);
  });

  it("all indexes 0–7 return valid color tokens", () => {
    for (let i = 0; i <= 7; i++) {
      const c = sliceColor({ label: "x", value: 1 }, i);
      expect(c).toMatch(COLOR_TOKEN);
    }
  });
});

// ── chart-helpers: buildColorScale ───────────────────────────────────────────

describe("buildColorScale", () => {
  const MONO = buildMonochromeScale(16);

  it("value=0 returns first palette color", () => {
    expect(buildColorScale(0, MONO)).toBe(MONO[0]);
  });

  it("value=1 returns last palette color", () => {
    expect(buildColorScale(1, MONO)).toBe(MONO[MONO.length - 1]);
  });

  it("value=0.5 returns a mid-tone valid hex", () => {
    const mid = buildColorScale(0.5, MONO);
    expect(mid).toMatch(/^#[0-9a-f]{6}$/i);
  });

  it("clamps negative values to 0 — no crash", () => {
    expect(buildColorScale(-5, MONO)).toBe(buildColorScale(0, MONO));
  });

  it("clamps values > 1 to 1 — no crash", () => {
    expect(buildColorScale(999, MONO)).toBe(buildColorScale(1, MONO));
  });

  it("NaN clamps to 0 — no crash", () => {
    expect(buildColorScale(NaN, MONO)).toBe(buildColorScale(0, MONO));
  });

  it("empty palette returns fallback #e5e5e5 — no crash", () => {
    expect(buildColorScale(0.5, [])).toBe("#e5e5e5");
  });

  it("single-entry palette always returns that entry", () => {
    expect(buildColorScale(0, ["#ff0000"])).toBe("#ff0000");
    expect(buildColorScale(1, ["#ff0000"])).toBe("#ff0000");
    expect(buildColorScale(0.5, ["#ff0000"])).toBe("#ff0000");
  });

  it("severity scale output is all valid hex", () => {
    const sev = buildSeverityScale(16);
    for (let i = 0; i <= 10; i++) {
      expect(buildColorScale(i / 10, sev)).toMatch(/^#[0-9a-f]{6}$/i);
    }
  });
});
