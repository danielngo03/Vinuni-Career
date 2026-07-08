"use client";

import { useState } from "react";
import { buildMonochromeScale, buildSeverityScale } from "./chart-theme";
import { buildColorScale } from "./chart-helpers";

// Re-export pure helper so callers can import from the component path.
export { buildColorScale };

// ── Types ─────────────────────────────────────────────────────────────────────

export type HeatmapColorScale = "monochrome" | "severity";

export interface HeatmapCell {
  x: string;
  y: string;
  value: number;
}

export interface HeatmapProps {
  cells: HeatmapCell[];
  xLabels: string[];
  yLabels: string[];
  /** Chart height in pixels. Defaults to 240. */
  height?: number;
  /** Color scale mode. "monochrome" = gray ramp; "severity" = amber→red. */
  colorScale?: HeatmapColorScale;
  /** Accessible label for the chart wrapper. */
  ariaLabel?: string;
  /** Text shown when cells is empty. */
  emptyLabel?: string;
}

// ── Component ─────────────────────────────────────────────────────────────────

const Y_LABEL_W = 56;
const X_LABEL_H = 24;
const CELL_GAP = 2;

/**
 * Day×hour style heatmap — custom SVG grid (recharts has no native heatmap).
 *
 * - Monochrome (light gray → ink) or severity (amber → red) color scale.
 * - Hover tooltip per cell.
 * - role="img" + aria-label.
 * - Graceful empty state — no crash when cells=[].
 */
export function Heatmap({
  cells,
  xLabels,
  yLabels,
  height = 240,
  colorScale = "monochrome",
  ariaLabel = "Heatmap chart",
  emptyLabel = "No data",
}: HeatmapProps) {
  const [tooltip, setTooltip] = useState<{
    x: number;
    y: number;
    cell: HeatmapCell;
  } | null>(null);

  if (cells.length === 0 || xLabels.length === 0 || yLabels.length === 0) {
    return (
      <div
        role="img"
        aria-label={ariaLabel}
        style={{ height }}
        className="flex items-center justify-center rounded-lg border border-dashed border-[var(--border-default)] text-xs text-[var(--text-muted)]"
      >
        {emptyLabel}
      </div>
    );
  }

  // Build a value map for O(1) lookup: `${x}::${y}` → value
  const valueMap = new Map<string, number>();
  for (const c of cells) {
    valueMap.set(`${c.x}::${c.y}`, c.value);
  }

  const allValues = cells.map((c) => (Number.isFinite(c.value) ? c.value : 0));
  const maxVal = allValues.length > 0 ? Math.max(...allValues) : 1;
  const effectiveMax = maxVal === 0 ? 1 : maxVal;

  // Build the palette once
  const PALETTE_STEPS = 16;
  const palette =
    colorScale === "severity"
      ? buildSeverityScale(PALETTE_STEPS)
      : buildMonochromeScale(PALETTE_STEPS);

  const usableH = height - X_LABEL_H;
  const cellH = (usableH - (yLabels.length - 1) * CELL_GAP) / yLabels.length;

  // ViewBox units: 10 units per label slot for proportional scaling
  const UNITS_W = xLabels.length * 10 + Y_LABEL_W / 10;
  const COL_W = (UNITS_W * 10 - Y_LABEL_W) / xLabels.length;

  return (
    <div
      role="img"
      aria-label={ariaLabel}
      style={{ width: "100%", height, position: "relative" }}
      onMouseLeave={() => setTooltip(null)}
    >
      <svg
        width="100%"
        height={height}
        viewBox={`0 0 ${UNITS_W * 10} ${height}`}
        preserveAspectRatio="xMidYMid meet"
        style={{ display: "block" }}
      >
        {/* X-axis labels */}
        {xLabels.map((xLabel, xi) => {
          const cx = Y_LABEL_W + xi * COL_W + COL_W / 2;
          return (
            <text
              key={`xl-${xLabel}`}
              x={cx}
              y={height - 4}
              textAnchor="middle"
              fontSize={9}
              fill="#737373"
              fontFamily="inherit"
            >
              {xLabel}
            </text>
          );
        })}

        {/* Y-axis labels + cells */}
        {yLabels.map((yLabel, yi) => {
          const cy = yi * (cellH + CELL_GAP);
          return (
            <g key={`row-${yLabel}`}>
              {/* Y label */}
              <text
                x={Y_LABEL_W - 6}
                y={cy + cellH / 2}
                textAnchor="end"
                dominantBaseline="middle"
                fontSize={9}
                fill="#737373"
                fontFamily="inherit"
              >
                {yLabel}
              </text>

              {/* Cells for this row */}
              {xLabels.map((xLabel, xi) => {
                const rawVal = valueMap.get(`${xLabel}::${yLabel}`) ?? 0;
                const norm = (Number.isFinite(rawVal) ? rawVal : 0) / effectiveMax;
                const fill = buildColorScale(norm, palette);
                const cellX = Y_LABEL_W + xi * COL_W + CELL_GAP / 2;

                return (
                  <rect
                    key={`cell-${xLabel}-${yLabel}`}
                    x={cellX}
                    y={cy}
                    width={Math.max(1, COL_W - CELL_GAP)}
                    height={Math.max(1, cellH - CELL_GAP)}
                    rx={2}
                    fill={fill}
                    style={{ cursor: "pointer" }}
                    onMouseEnter={(e) => {
                      const rect = (e.currentTarget as SVGElement).getBoundingClientRect();
                      setTooltip({
                        x: rect.left + rect.width / 2,
                        y: rect.top,
                        cell: { x: xLabel, y: yLabel, value: rawVal },
                      });
                    }}
                    onMouseLeave={() => setTooltip(null)}
                  />
                );
              })}
            </g>
          );
        })}
      </svg>

      {/* Tooltip overlay */}
      {tooltip !== null && (
        <div
          style={{
            position: "fixed",
            left: tooltip.x,
            top: tooltip.y - 8,
            transform: "translate(-50%, -100%)",
            pointerEvents: "none",
            background: "#ffffff",
            border: "1px solid #e5e5e5",
            borderRadius: 6,
            boxShadow: "0 4px 16px rgba(0,0,0,0.07)",
            padding: "6px 10px",
            fontFamily: "'Plus Jakarta Sans', 'Inter', system-ui, sans-serif",
            fontSize: 12,
            color: "#171717",
            zIndex: 50,
            whiteSpace: "nowrap",
          }}
        >
          <span style={{ color: "#525252" }}>
            {tooltip.cell.y} · {tooltip.cell.x}
          </span>
          <span
            style={{
              marginLeft: 8,
              fontFamily: "'JetBrains Mono', monospace",
              fontWeight: 600,
            }}
          >
            {new Intl.NumberFormat("vi-VN", {
              notation: "compact",
              maximumFractionDigits: 1,
            }).format(tooltip.cell.value)}
          </span>
        </div>
      )}
    </div>
  );
}
