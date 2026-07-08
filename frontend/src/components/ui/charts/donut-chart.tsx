"use client";

import {
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
  Tooltip,
  Legend,
  type TooltipProps,
} from "recharts";
import type { NameType, ValueType } from "recharts/types/component/DefaultTooltipContent";
import { CHART_TOOLTIP_STYLE } from "./chart-theme";
import { donutTotal, sliceColor } from "./chart-helpers";

// Re-export pure helpers so callers can import from the component path.
export { donutTotal, sliceColor };
export type { DonutSliceData } from "./chart-helpers";

// ── Types ─────────────────────────────────────────────────────────────────────

export type { ChartTone } from "./chart-theme";

import type { ChartTone } from "./chart-theme";

export interface DonutSlice {
  label: string;
  value: number;
  /** Explicit hex override. Takes precedence over tone. */
  color?: string;
  /** Semantic tone — resolved to hex via chart-theme. */
  tone?: ChartTone;
}

export interface DonutChartProps {
  data: DonutSlice[];
  /** Chart height in pixels. Defaults to 240. */
  height?: number;
  /** Accessible label for the chart wrapper. */
  ariaLabel?: string;
  /** Text shown when data is empty. */
  emptyLabel?: string;
}

// ── Custom tooltip ────────────────────────────────────────────────────────────

function DonutTooltip({ active, payload }: TooltipProps<ValueType, NameType>) {
  if (!active || !payload || payload.length === 0) return null;
  const entry = payload[0];
  if (!entry) return null;
  return (
    <div style={CHART_TOOLTIP_STYLE}>
      <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
        <span
          style={{
            display: "inline-block",
            width: 8,
            height: 8,
            borderRadius: "50%",
            background: String((entry.payload as { fill?: string } | undefined)?.fill ?? "var(--chart-series-1)"),
            flexShrink: 0,
          }}
        />
        <span style={{ color: "var(--chart-label)", fontSize: 12 }}>{String(entry.name ?? "")}</span>
        <span
          style={{
            marginLeft: "auto",
            paddingLeft: 12,
            fontFamily: "'JetBrains Mono', monospace",
            fontWeight: 600,
            fontSize: 12,
            color: "var(--chart-tooltip-text)",
          }}
        >
          {new Intl.NumberFormat("vi-VN", {
            notation: "compact",
            maximumFractionDigits: 1,
          }).format(Number(entry.value ?? 0))}
        </span>
      </div>
    </div>
  );
}

// ── Component ─────────────────────────────────────────────────────────────────

/**
 * Monochrome donut chart with a center total.
 *
 * - Slices use the gray ramp + optional semantic tone.
 * - Legend with label + value.
 * - Center total rendered via SVG text elements inside PieChart.
 * - role="img" + aria-label.
 * - Graceful empty state — no crash when data=[].
 */
export function DonutChart({
  data,
  height = 240,
  ariaLabel = "Donut chart",
  emptyLabel = "No data",
}: DonutChartProps) {
  if (data.length === 0) {
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

  const total = donutTotal(data);
  const formattedTotal = new Intl.NumberFormat("vi-VN", {
    notation: "compact",
    maximumFractionDigits: 1,
  }).format(total);

  const innerRadius = Math.round(height * 0.22);
  const outerRadius = Math.round(height * 0.36);

  return (
    <div role="img" aria-label={ariaLabel} style={{ width: "100%", height }}>
      <ResponsiveContainer width="100%" height="100%">
        <PieChart>
          {/* Center total — SVG text floats above the donut hole */}
          <text
            x="50%"
            y="42%"
            textAnchor="middle"
            dominantBaseline="middle"
            style={{
              fontFamily: "'JetBrains Mono', monospace",
              fontSize: 18,
              fontWeight: 700,
              fill: "var(--chart-tooltip-text)",
            }}
          >
            {formattedTotal}
          </text>
          <text
            x="50%"
            y="52%"
            textAnchor="middle"
            dominantBaseline="middle"
            style={{ fontFamily: "inherit", fontSize: 11, fill: "var(--chart-muted)" }}
          >
            total
          </text>
          <Pie
            data={data.map((d) => ({ ...d, name: d.label }))}
            cx="50%"
            cy="45%"
            innerRadius={innerRadius}
            outerRadius={outerRadius}
            dataKey="value"
            strokeWidth={0}
          >
            {data.map((entry, index) => (
              <Cell
                key={`cell-${entry.label}`}
                fill={sliceColor(entry, index)}
              />
            ))}
          </Pie>
          <Tooltip content={<DonutTooltip />} />
          <Legend
            wrapperStyle={{ fontSize: 11, color: "var(--chart-label)", paddingTop: 4 }}
            iconType="circle"
            iconSize={8}
            formatter={(value: string) => (
              <span style={{ color: "var(--chart-label)" }}>{value}</span>
            )}
          />
        </PieChart>
      </ResponsiveContainer>
    </div>
  );
}
