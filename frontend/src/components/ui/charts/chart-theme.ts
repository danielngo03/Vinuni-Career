/**
 * Shared monochrome chart theme for VinUni admin console.
 *
 * Design source: docs/DESIGN.md §1.1.2 v9 "Monochrome"
 *
 * Primary action color: ink #171717
 * Hierarchy: full --gray-* ramp
 * Semantic colors ONLY for meaning:
 *   teal  --teal-600 (#059669)  = success / healthy
 *   amber --amber-600 (#d97706) = warning / time-sensitive
 *   red   --brand-red (#c83538) = error / destructive
 *
 * Numbers / metric labels use JetBrains Mono via --font-mono.
 */

/** Primary ink for first/main series. */
export const CHART_INK = "#171717";

/** Gray ramp: use in order for secondary, tertiary, ... series. */
export const CHART_GRAY_SERIES = [
  "#404040", // gray-700 – second series
  "#737373", // gray-500 – third series
  "#a3a3a3", // gray-400 – fourth series
  "#d4d4d4", // gray-300 – fifth series
  "#e5e5e5", // gray-200 – sixth series
] as const;

/** Semantic hues — use ONLY where they carry meaning, not decoration. */
export const CHART_TEAL = "#059669"; // success / healthy
export const CHART_AMBER = "#d97706"; // warning / time-sensitive
export const CHART_RED = "#c83538"; // error / destructive

/** Grid / axis styling. */
export const CHART_GRID_COLOR = "#e5e5e5"; // gray-200
export const CHART_AXIS_TICK_COLOR = "#737373"; // gray-500
export const CHART_AXIS_LINE_COLOR = "#e5e5e5"; // gray-200

/** Reference line (dashed neutral threshold). */
export const CHART_REFERENCE_COLOR = "#a3a3a3"; // gray-400

/** Tooltip surface styling (CSS values, not variables, for recharts inline styles). */
export const CHART_TOOLTIP_STYLE = {
  background: "#ffffff",
  border: "1px solid #e5e5e5",
  borderRadius: "6px",
  boxShadow: "0 4px 16px rgba(0,0,0,0.07), 0 2px 6px rgba(0,0,0,0.04)",
  padding: "8px 12px",
  fontFamily: "'Plus Jakarta Sans', 'Inter', system-ui, sans-serif",
  fontSize: "12px",
  color: "#171717",
} as const;

export const CHART_TOOLTIP_CURSOR_STYLE = {
  fill: "rgba(23,23,23,0.04)",
} as const;

/** Monotone curve interpolation — smoother than linear, no over-shoot. */
export const CHART_CURVE_TYPE = "monotone" as const;

/**
 * Given a 0-indexed series position, return the appropriate color.
 * Position 0 → ink; positions 1+ → gray ramp (clamped at last gray).
 */
export function seriesColor(index: number): string {
  if (index === 0) return CHART_INK;
  const grayIndex = Math.min(index - 1, CHART_GRAY_SERIES.length - 1);
  return CHART_GRAY_SERIES[grayIndex] ?? CHART_GRAY_SERIES[CHART_GRAY_SERIES.length - 1] ?? "#d4d4d4";
}

/**
 * Semantic tone → hex color.
 * Falls through to neutral gray when tone is undefined.
 */
export type ChartTone = "success" | "warning" | "error" | "neutral";

export function toneColor(tone: ChartTone | undefined, fallback: string = CHART_INK): string {
  switch (tone) {
    case "success":
      return CHART_TEAL;
    case "warning":
      return CHART_AMBER;
    case "error":
      return CHART_RED;
    default:
      return fallback;
  }
}

/**
 * Build a CSS linear-gradient string for donut/heatmap color scales.
 * Monochrome by default (light gray → ink); override with semantic hues.
 */
export function buildMonochromeScale(steps: number): string[] {
  // Evenly spaced between gray-100 (#f5f5f5) and ink (#171717)
  const start = 0xf5; // 245 decimal
  const end = 0x17; // 23 decimal
  return Array.from({ length: steps }, (_, i) => {
    const t = steps === 1 ? 1 : i / (steps - 1);
    const val = Math.round(start + (end - start) * t);
    const hex = val.toString(16).padStart(2, "0");
    return `#${hex}${hex}${hex}`;
  });
}

/**
 * Amber→red severity scale for heatmap error intensity.
 */
export function buildSeverityScale(steps: number): string[] {
  if (steps <= 0) return [];
  if (steps === 1) return [CHART_AMBER];
  const palette = [
    "#fef3c7", // amber-50 tint
    "#fde68a", // amber-200
    "#fbbf24", // amber-400
    "#d97706", // amber-600
    "#b45309", // amber-700
    "#c83538", // brand-red
    "#7f2629", // red-800
  ] as const;
  const result: string[] = [];
  for (let i = 0; i < steps; i++) {
    const t = i / (steps - 1);
    const rawIdx = t * (palette.length - 1);
    const lo = Math.floor(rawIdx);
    const hi = Math.min(lo + 1, palette.length - 1);
    const frac = rawIdx - lo;
    // Lerp between two adjacent palette entries
    const loColor = palette[lo] ?? palette[palette.length - 1] ?? "#d97706";
    const hiColor = palette[hi] ?? palette[palette.length - 1] ?? "#d97706";
    result.push(lerpHex(loColor, hiColor, frac));
  }
  return result;
}

function hexToRgb(hex: string): [number, number, number] {
  const clean = hex.replace("#", "");
  const r = parseInt(clean.slice(0, 2), 16);
  const g = parseInt(clean.slice(2, 4), 16);
  const b = parseInt(clean.slice(4, 6), 16);
  return [
    isNaN(r) ? 0 : r,
    isNaN(g) ? 0 : g,
    isNaN(b) ? 0 : b,
  ];
}

function lerpHex(a: string, b: string, t: number): string {
  const [r1, g1, b1] = hexToRgb(a);
  const [r2, g2, b2] = hexToRgb(b);
  const r = Math.round(r1 + (r2 - r1) * t);
  const g = Math.round(g1 + (g2 - g1) * t);
  const bVal = Math.round(b1 + (b2 - b1) * t);
  return `#${r.toString(16).padStart(2, "0")}${g.toString(16).padStart(2, "0")}${bVal.toString(16).padStart(2, "0")}`;
}

/** Exported for test coverage. */
export { lerpHex, hexToRgb };
