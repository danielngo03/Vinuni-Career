"use client";

import {
  ResponsiveContainer,
  ComposedChart,
  Area,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  type TooltipProps,
} from "recharts";
import type { NameType, ValueType } from "recharts/types/component/DefaultTooltipContent";
import {
  CHART_INK,
  CHART_AMBER,
  CHART_AXIS_TICK_COLOR,
  CHART_AXIS_LINE_COLOR,
  CHART_GRID_COLOR,
  CHART_TOOLTIP_STYLE,
  CHART_TOOLTIP_CURSOR_STYLE,
  CHART_CURVE_TYPE,
} from "./chart-theme";
import { formatTick } from "./chart-helpers";

// ── Types ─────────────────────────────────────────────────────────────────────

export interface PercentileBandDataPoint {
  [key: string]: string | number | undefined;
}

export interface PercentileBandChartProps {
  data: PercentileBandDataPoint[];
  /** Which key in each data point is the X-axis value. */
  xKey: string;
  /** Data key for the p50 (median) series. */
  p50Key: string;
  /** Data key for the p95 series. */
  p95Key: string;
  /** Data key for the p99 series. */
  p99Key: string;
  /** Chart height in pixels. Defaults to 240. */
  height?: number;
  /** Accessible label for the chart wrapper. */
  ariaLabel?: string;
  /** Text shown when data is empty. */
  emptyLabel?: string;
}

// ── Custom tooltip ────────────────────────────────────────────────────────────

function PercentileTooltip({
  active,
  payload,
  label,
  p50Key,
  p95Key,
  p99Key,
}: TooltipProps<ValueType, NameType> & {
  p50Key: string;
  p95Key: string;
  p99Key: string;
}) {
  if (!active || !payload || payload.length === 0) return null;

  const get = (key: string) =>
    payload.find((e) => e.dataKey === key)?.value;

  const p50 = get(p50Key);
  const p95 = get(p95Key);
  const p99 = get(p99Key);

  return (
    <div style={CHART_TOOLTIP_STYLE}>
      <p
        style={{
          marginBottom: 6,
          fontWeight: 600,
          fontSize: 11,
          color: "#525252",
          letterSpacing: "0.06em",
          textTransform: "uppercase",
        }}
      >
        {String(label ?? "")}
      </p>
      {[
        { label: "p50", value: p50, color: CHART_INK },
        { label: "p95", value: p95, color: CHART_AMBER },
        { label: "p99", value: p99, color: CHART_AMBER },
      ].map(({ label: lbl, value, color }) =>
        value !== undefined ? (
          <div
            key={lbl}
            style={{ display: "flex", alignItems: "center", gap: 6, marginTop: 2 }}
          >
            <span
              style={{
                display: "inline-block",
                width: 8,
                height: 8,
                borderRadius: "50%",
                background: color,
                flexShrink: 0,
              }}
            />
            <span style={{ color: "#525252", fontSize: 12 }}>{lbl}</span>
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
              {formatTick(Number(value), "ms")}
            </span>
          </div>
        ) : null,
      )}
    </div>
  );
}

// ── Component ─────────────────────────────────────────────────────────────────

/**
 * Latency percentile band chart.
 *
 * - p95–p99 shaded area with amber accent (upper warning band).
 * - p50 line in ink (primary / healthy).
 * - p95 line in amber (subtle boundary).
 * - Y-axis formatted as latency (ms / s).
 * - role="img" + aria-label.
 * - Graceful empty state — no crash when data=[].
 */
export function PercentileBandChart({
  data,
  xKey,
  p50Key,
  p95Key,
  p99Key,
  height = 240,
  ariaLabel = "Percentile band chart",
  emptyLabel = "No data",
}: PercentileBandChartProps) {
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

  return (
    <div role="img" aria-label={ariaLabel} style={{ width: "100%", height }}>
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={data} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
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
            tickFormatter={(v: number) => formatTick(v, "ms")}
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
            content={
              <PercentileTooltip
                p50Key={p50Key}
                p95Key={p95Key}
                p99Key={p99Key}
              />
            }
            cursor={CHART_TOOLTIP_CURSOR_STYLE}
          />
          <Legend
            wrapperStyle={{ fontSize: 11, color: "#525252", paddingTop: 8 }}
            iconType="circle"
            iconSize={8}
          />

          {/*
            p95–p99 shaded band: render as two Area series.
            recharts does not have a native band fill between two data keys,
            so we use a transparent area for p95 base and the amber tinted area
            for p99, stacked visually (not stacked numerically — baseLine is p95).
            We approximate by rendering p99 as area with low opacity and p95 as
            a line, which gives the "upper band" shaded effect.
          */}
          <Area
            type={CHART_CURVE_TYPE}
            dataKey={p99Key}
            name="p99"
            stroke={CHART_AMBER}
            strokeWidth={1.5}
            fill={CHART_AMBER}
            fillOpacity={0.10}
            dot={false}
            activeDot={{ r: 3, strokeWidth: 0 }}
          />
          <Line
            type={CHART_CURVE_TYPE}
            dataKey={p95Key}
            name="p95"
            stroke={CHART_AMBER}
            strokeWidth={1}
            strokeDasharray="3 2"
            dot={false}
            activeDot={{ r: 3, strokeWidth: 0 }}
          />
          {/* p50 median — primary ink line, rendered last (on top) */}
          <Line
            type={CHART_CURVE_TYPE}
            dataKey={p50Key}
            name="p50"
            stroke={CHART_INK}
            strokeWidth={2}
            dot={false}
            activeDot={{ r: 4, strokeWidth: 0 }}
          />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}
