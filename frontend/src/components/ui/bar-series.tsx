import { cn } from "@/lib/utils";
import {
  computeBarGeometry,
  type BarDataPoint,
  type BarGeometryEntry,
  type ComputeBarGeometryOpts,
} from "./bar-series-math";

// Re-export pure helpers and types so callers can import from the component
// path without going through the math file directly.
export { computeBarGeometry };
export type { BarDataPoint, BarGeometryEntry, ComputeBarGeometryOpts };

export interface BarSeriesProps {
  data: BarDataPoint[];
  /** Optional numeric reference line (e.g. budget target). */
  referenceLine?: number;
  /** Value formatter — defaults to the raw number. */
  format?: (value: number) => string;
  /** Emphasize the max-value bar with ink colour. Defaults to true. */
  emphasizeMax?: boolean;
  /** Accessible label for the chart region. */
  ariaLabel?: string;
  className?: string;
}

/**
 * Vertical bar chart primitive using inline SVG with design tokens.
 *
 * - Monochrome: max bar uses ink (#171717), others use --gray-300.
 * - Optional dashed reference line (amber, matches budget/threshold semantics).
 * - Empty data renders a small "no data" placeholder — no crash, no NaN.
 * - Accessible: role="img" + aria-label.
 * - Responsive: width:100% / viewBox scaling.
 * - No external dependencies.
 */
export function BarSeries({
  data,
  referenceLine,
  format,
  emphasizeMax = true,
  ariaLabel = "Bar chart",
  className,
}: BarSeriesProps) {
  const fmt = format ?? ((v: number) => String(v));

  if (data.length === 0) {
    return (
      <div
        role="img"
        aria-label={ariaLabel}
        className={cn(
          "flex h-24 items-center justify-center rounded-lg border border-dashed border-[var(--border-default)] text-xs text-[var(--text-muted)]",
          className,
        )}
      >
        No data
      </div>
    );
  }

  const bars = computeBarGeometry(data);
  const maxValue = Math.max(...data.map((d) => d.value));
  const effectiveMax = maxValue === 0 ? 1 : maxValue;

  // SVG coordinate system constants
  const BAR_W = 24;
  const GAP = 8;
  const CHART_H = 80;
  const LABEL_H = 16;
  const VALUE_H = 14;
  const svgW = data.length * BAR_W + (data.length - 1) * GAP;
  const svgH = CHART_H + LABEL_H + VALUE_H;

  const refLineY =
    referenceLine !== undefined
      ? CHART_H - (Math.min(referenceLine, effectiveMax) / effectiveMax) * CHART_H
      : null;

  return (
    <svg
      role="img"
      aria-label={ariaLabel}
      viewBox={`0 0 ${svgW} ${svgH}`}
      preserveAspectRatio="xMidYMid meet"
      className={cn("w-full max-w-full", className)}
      style={{ display: "block" }}
    >
      {bars.map((bar, i) => {
        const x = i * (BAR_W + GAP);
        const barH = (bar.heightPct / 100) * CHART_H;
        const y = CHART_H - barH;
        const fill = emphasizeMax && bar.isMax ? "#171717" : "var(--gray-300)";

        return (
          <g key={bar.label}>
            {/* Value label above bar */}
            <text
              x={x + BAR_W / 2}
              y={y - 3}
              textAnchor="middle"
              fontSize={8}
              fill="var(--text-secondary, #6b7280)"
              fontFamily="inherit"
            >
              {fmt(bar.value)}
            </text>

            {/* Bar rect */}
            <rect
              x={x}
              y={y}
              width={BAR_W}
              height={barH}
              rx={3}
              fill={fill}
            />

            {/* Axis label */}
            <text
              x={x + BAR_W / 2}
              y={CHART_H + LABEL_H}
              textAnchor="middle"
              fontSize={8}
              fill="var(--text-muted, #9ca3af)"
              fontFamily="inherit"
            >
              {bar.label}
            </text>
          </g>
        );
      })}

      {/* Reference line */}
      {refLineY !== null && (
        <line
          x1={0}
          y1={refLineY}
          x2={svgW}
          y2={refLineY}
          stroke="var(--amber-500, #f59e0b)"
          strokeWidth={1}
          strokeDasharray="4 3"
        />
      )}
    </svg>
  );
}
