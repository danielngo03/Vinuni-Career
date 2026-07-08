"use client";

import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  type TooltipProps,
} from "recharts";
import type { NameType, ValueType } from "recharts/types/component/DefaultTooltipContent";
import {
  CHART_AXIS_TICK_COLOR,
  CHART_AXIS_LINE_COLOR,
  CHART_GRID_COLOR,
  CHART_TOOLTIP_STYLE,
  CHART_TOOLTIP_CURSOR_STYLE,
  seriesColor,
  toneColor,
  type ChartTone,
} from "./chart-theme";
import { formatTick } from "./chart-helpers";
import type { FormatKind } from "./chart-helpers";

// ── Types ─────────────────────────────────────────────────────────────────────

export interface StackedBarDataPoint {
  [key: string]: string | number | undefined;
}

export interface StackedBarSeriesDef {
  key: string;
  label: string;
  /** Explicit hex override — takes precedence over tone and ramp. */
  color?: string;
  /** Semantic tone — resolved to hex. */
  tone?: ChartTone;
}

export interface StackedBarChartProps {
  data: StackedBarDataPoint[];
  /** Which key in each data point is the X-axis label. */
  xKey: string;
  /** Series definitions. */
  series: StackedBarSeriesDef[];
  /** Chart height in pixels. Defaults to 240. */
  height?: number;
  /** Format kind for Y-axis tick labels and tooltip values. */
  format?: FormatKind;
  /** Accessible label for the chart wrapper. */
  ariaLabel?: string;
  /** Text shown when data is empty. */
  emptyLabel?: string;
}

// ── Color resolution ──────────────────────────────────────────────────────────

function resolveBarColor(s: StackedBarSeriesDef, index: number): string {
  if (s.color) return s.color;
  if (s.tone) return toneColor(s.tone);
  return seriesColor(index);
}

// ── Custom tooltip ────────────────────────────────────────────────────────────

function StackedTooltip({
  active,
  payload,
  label,
  format: fmt = "number",
}: TooltipProps<ValueType, NameType> & { format?: FormatKind }) {
  if (!active || !payload || payload.length === 0) return null;
  const total = payload.reduce((acc, e) => acc + Number(e.value ?? 0), 0);
  return (
    <div style={CHART_TOOLTIP_STYLE}>
      <p
        style={{
          marginBottom: 4,
          fontWeight: 600,
          fontSize: 11,
          color: "#525252",
          letterSpacing: "0.06em",
          textTransform: "uppercase",
        }}
      >
        {String(label ?? "")}
      </p>
      {payload.map((entry) => (
        <div
          key={String(entry.dataKey ?? entry.name)}
          style={{ display: "flex", alignItems: "center", gap: 6, marginTop: 2 }}
        >
          <span
            style={{
              display: "inline-block",
              width: 8,
              height: 8,
              borderRadius: 2,
              background: String(entry.color ?? "#171717"),
              flexShrink: 0,
            }}
          />
          <span style={{ color: "#525252", fontSize: 12 }}>{String(entry.name ?? "")}</span>
          <span
            style={{
              marginLeft: "auto",
              paddingLeft: 12,
              fontFamily: "'JetBrains Mono', monospace",
              fontWeight: 600,
              fontSize: 12,
              color: "#171717",
            }}
          >
            {formatTick(Number(entry.value ?? 0), fmt)}
          </span>
        </div>
      ))}
      {payload.length > 1 && (
        <div
          style={{
            marginTop: 6,
            paddingTop: 6,
            borderTop: "1px solid #e5e5e5",
            display: "flex",
            justifyContent: "space-between",
          }}
        >
          <span style={{ fontSize: 11, color: "#737373" }}>Total</span>
          <span
            style={{
              fontFamily: "'JetBrains Mono', monospace",
              fontWeight: 700,
              fontSize: 12,
              color: "#171717",
            }}
          >
            {formatTick(total, fmt)}
          </span>
        </div>
      )}
    </div>
  );
}

// ── Component ─────────────────────────────────────────────────────────────────

/**
 * Stacked bar chart — monochrome VinUni admin theme.
 *
 * - Stacks all series defined in `series` prop.
 * - Colors: gray ramp by default; series-level `color`/`tone` overrides.
 * - Tooltip shows per-series values + total.
 * - role="img" + aria-label.
 * - Graceful empty state — no crash when data=[].
 */
export function StackedBarChart({
  data,
  xKey,
  series,
  height = 240,
  format: fmt = "number",
  ariaLabel = "Stacked bar chart",
  emptyLabel = "No data",
}: StackedBarChartProps) {
  if (data.length === 0 || series.length === 0) {
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

  return (
    <div role="img" aria-label={ariaLabel} style={{ width: "100%", height }}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart
          data={data}
          margin={{ top: 4, right: 8, bottom: 0, left: 0 }}
          barCategoryGap="30%"
        >
          <CartesianGrid
            strokeDasharray="3 3"
            stroke={CHART_GRID_COLOR}
            vertical={false}
          />
          <XAxis
            dataKey={xKey}
            tick={{ fill: CHART_AXIS_TICK_COLOR, fontSize: 11 }}
            axisLine={{ stroke: CHART_AXIS_LINE_COLOR }}
            tickLine={false}
            dy={4}
          />
          <YAxis
            tickFormatter={(v: number) => formatTick(v, fmt)}
            tick={{
              fill: CHART_AXIS_TICK_COLOR,
              fontSize: 11,
              fontFamily: "'JetBrains Mono', monospace",
            }}
            axisLine={false}
            tickLine={false}
            width={56}
          />
          <Tooltip
            content={<StackedTooltip format={fmt} />}
            cursor={CHART_TOOLTIP_CURSOR_STYLE}
          />
          <Legend
            wrapperStyle={{ fontSize: 11, color: "#525252", paddingTop: 8 }}
            iconType="square"
            iconSize={8}
          />
          {series.map((s, idx) => (
            <Bar
              key={s.key}
              dataKey={s.key}
              name={s.label}
              stackId="a"
              fill={resolveBarColor(s, idx)}
              radius={idx === series.length - 1 ? [3, 3, 0, 0] : [0, 0, 0, 0]}
            />
          ))}
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
