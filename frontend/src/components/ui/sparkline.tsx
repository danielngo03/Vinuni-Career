import { cn } from "@/lib/utils";
import {
  computeSparklinePoints,
  type SparklinePoint,
} from "./sparkline-math";

// Re-export so callers can import from the component path.
export { computeSparklinePoints };
export type { SparklinePoint };

export interface SparklineProps {
  data: number[];
  /** Accessible label for the chart. */
  ariaLabel?: string;
  className?: string;
}

/**
 * Inline SVG polyline sparkline — fits the container width.
 *
 * - Monochrome: line uses ink (#171717).
 * - Empty / single-point: renders gracefully (no crash, no NaN).
 * - Accessible: role="img" + aria-label.
 * - Responsive: width:100%, viewBox scaling.
 * - No external dependencies.
 */
export function Sparkline({
  data,
  ariaLabel = "Trend sparkline",
  className,
}: SparklineProps) {
  const W = 120;
  const H = 32;

  if (data.length === 0) {
    return (
      <svg
        role="img"
        aria-label={ariaLabel}
        viewBox={`0 0 ${W} ${H}`}
        preserveAspectRatio="none"
        className={cn("w-full max-w-full", className)}
        style={{ display: "block" }}
      >
        <line
          x1={0}
          y1={H / 2}
          x2={W}
          y2={H / 2}
          stroke="var(--gray-200, #e5e7eb)"
          strokeWidth={1.5}
          strokeDasharray="4 3"
        />
      </svg>
    );
  }

  const points = computeSparklinePoints(data, W, H);
  const pointsStr = points.map((p) => `${p.x},${p.y}`).join(" ");

  return (
    <svg
      role="img"
      aria-label={ariaLabel}
      viewBox={`0 0 ${W} ${H}`}
      preserveAspectRatio="none"
      className={cn("w-full max-w-full", className)}
      style={{ display: "block" }}
    >
      <polyline
        points={pointsStr}
        fill="none"
        stroke="#171717"
        strokeWidth={1.5}
        strokeLinejoin="round"
        strokeLinecap="round"
      />
    </svg>
  );
}
