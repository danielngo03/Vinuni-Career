/**
 * Pure geometry helpers for Sparkline — no React/JSX dependency.
 * Importable from tests running in a node environment.
 */

export interface SparklinePoint {
  x: number;
  y: number;
}

/**
 * Map a number[] to SVG polyline point coordinates.
 *
 * - Empty array → [].
 * - Single element → two coincident-ish points at mid-height (safe polyline).
 * - NaN / Infinity values → clamped to 0.
 * - Constant series (all same value) → horizontal line at mid-height, no NaN.
 */
export function computeSparklinePoints(
  data: number[],
  width: number,
  height: number,
): SparklinePoint[] {
  if (data.length === 0) return [];

  const safeData = data.map((v) => (Number.isFinite(v) ? v : 0));

  if (safeData.length === 1) {
    return [
      { x: 0, y: height / 2 },
      { x: width, y: height / 2 },
    ];
  }

  const minVal = Math.min(...safeData);
  const maxVal = Math.max(...safeData);
  const range = maxVal - minVal === 0 ? 1 : maxVal - minVal;

  return safeData.map((v, i) => ({
    x: (i / (safeData.length - 1)) * width,
    y: height - ((v - minVal) / range) * height,
  }));
}
