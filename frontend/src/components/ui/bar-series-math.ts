/**
 * Pure geometry helpers for BarSeries — no React/JSX dependency.
 * Importable from tests running in a node environment.
 */

export interface BarDataPoint {
  label: string;
  value: number;
}

export interface BarGeometryEntry {
  label: string;
  value: number;
  /** Height as a percentage 0–100 relative to the max value. */
  heightPct: number;
  isMax: boolean;
}

export interface ComputeBarGeometryOpts {
  /** Minimum rendered height percentage so tiny bars remain visible. Default 2. */
  minHeightPct?: number;
}

/**
 * Compute per-bar geometry for BarSeries.
 *
 * - Empty input → [].
 * - All-zero input → no NaN (uses effective max of 1).
 * - `isMax` is true for every entry whose value equals the maximum.
 */
export function computeBarGeometry(
  data: BarDataPoint[],
  opts: ComputeBarGeometryOpts = {},
): BarGeometryEntry[] {
  if (data.length === 0) return [];

  const { minHeightPct = 2 } = opts;
  const maxValue = Math.max(...data.map((d) => d.value));
  const effectiveMax = maxValue === 0 ? 1 : maxValue;

  return data.map((d) => {
    const raw = (d.value / effectiveMax) * 100;
    return {
      label: d.label,
      value: d.value,
      heightPct: Math.max(minHeightPct, raw),
      isMax: d.value === maxValue,
    };
  });
}
