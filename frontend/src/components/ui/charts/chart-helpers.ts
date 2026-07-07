/**
 * Pure chart helper functions — no React/JSX dependency.
 * Importable from node test environments.
 */

import {
  CHART_INK,
  CHART_GRAY_SERIES,
  toneColor,
  buildMonochromeScale,
  type ChartTone,
} from "./chart-theme";

// ── formatTick ────────────────────────────────────────────────────────────────

export type FormatKind = "number" | "currency" | "ms" | "percent";

/**
 * Format a numeric axis/tooltip value.
 *
 * - "number"   → compact Vietnamese notation (1.2K, etc.)
 * - "currency" → compact VND
 * - "ms"       → latency: ms below 1000, s at/above 1000
 * - "percent"  → fixed 1 decimal + %
 * - Non-finite → "—"
 */
export function formatTick(value: number, kind: FormatKind = "number"): string {
  if (!Number.isFinite(value)) return "—";
  switch (kind) {
    case "currency":
      return new Intl.NumberFormat("vi-VN", {
        style: "currency",
        currency: "VND",
        notation: "compact",
        maximumFractionDigits: 1,
      }).format(value);
    case "ms":
      if (value >= 1000) return `${(value / 1000).toFixed(1)}s`;
      return `${Math.round(value)}ms`;
    case "percent":
      return `${value.toFixed(1)}%`;
    default:
      return new Intl.NumberFormat("vi-VN", {
        notation: "compact",
        maximumFractionDigits: 1,
      }).format(value);
  }
}

// ── donutTotal ────────────────────────────────────────────────────────────────

export interface DonutSliceData {
  label: string;
  value: number;
  color?: string;
  tone?: ChartTone;
}

/**
 * Compute the total of all slice values.
 * Returns 0 for empty input — no NaN.
 */
export function donutTotal(data: DonutSliceData[]): number {
  if (data.length === 0) return 0;
  return data.reduce((acc, d) => acc + (Number.isFinite(d.value) ? d.value : 0), 0);
}

/**
 * Resolve the fill color for a donut slice.
 * Priority: explicit `color` > semantic `tone` > gray ramp position.
 */
export function sliceColor(slice: DonutSliceData, index: number): string {
  if (slice.color) return slice.color;
  if (slice.tone) return toneColor(slice.tone);
  if (index === 0) return CHART_INK;
  const grayIdx = Math.min(index - 1, CHART_GRAY_SERIES.length - 1);
  return CHART_GRAY_SERIES[grayIdx] ?? "#d4d4d4";
}

// ── buildColorScale ───────────────────────────────────────────────────────────

/**
 * Given a normalized value in [0, 1] and a color palette array, return the
 * interpolated hex color.
 *
 * - 0 → first palette entry (lightest in monochrome scale)
 * - 1 → last palette entry (darkest / most intense)
 * - Out-of-range values are clamped.
 * - NaN is treated as 0.
 * - Empty palette returns fallback gray #e5e5e5.
 */
export function buildColorScale(
  value: number,
  palette: readonly string[],
): string {
  if (palette.length === 0) return "#e5e5e5";
  const clamped = Math.max(0, Math.min(1, Number.isFinite(value) ? value : 0));
  const rawIdx = clamped * (palette.length - 1);
  const lo = Math.floor(rawIdx);
  const hi = Math.min(lo + 1, palette.length - 1);
  const loColor = palette[lo] ?? palette[palette.length - 1] ?? "#e5e5e5";
  if (lo === hi) return loColor;
  const hiColor = palette[hi] ?? loColor;
  const frac = rawIdx - lo;
  return lerpHexLocal(loColor, hiColor, frac);
}

function lerpHexLocal(a: string, b: string, t: number): string {
  const h2r = (hex: string): [number, number, number] => {
    const c = hex.replace("#", "");
    const r = parseInt(c.slice(0, 2), 16);
    const g = parseInt(c.slice(2, 4), 16);
    const bv = parseInt(c.slice(4, 6), 16);
    return [isNaN(r) ? 0 : r, isNaN(g) ? 0 : g, isNaN(bv) ? 0 : bv];
  };
  const [r1, g1, b1] = h2r(a);
  const [r2, g2, b2] = h2r(b);
  const r = Math.round(r1 + (r2 - r1) * t);
  const g = Math.round(g1 + (g2 - g1) * t);
  const bVal = Math.round(b1 + (b2 - b1) * t);
  return `#${r.toString(16).padStart(2, "0")}${g.toString(16).padStart(2, "0")}${bVal.toString(16).padStart(2, "0")}`;
}

// Re-export monochrome scale for convenience in tests
export { buildMonochromeScale };
