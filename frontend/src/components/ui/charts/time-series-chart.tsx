"use client";

import {
  ResponsiveContainer,
  ComposedChart,
  Line,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ReferenceLine,
  type TooltipProps,
} from "recharts";
import type { NameType, ValueType } from "recharts/types/component/DefaultTooltipContent";
import {
  CHART_AXIS_TICK_COLOR,
  CHART_AXIS_LINE_COLOR,
  CHART_GRID_COLOR,
  CHART_REFERENCE_COLOR,
  CHART_TOOLTIP_STYLE,
  CHART_TOOLTIP_CURSOR_STYLE,
  CHART_CURVE_TYPE,
  seriesColor,
} from "./chart-theme";
import { formatTick } from "./chart-helpers";
import type { FormatKind } from "./chart-helpers";

// Re-export so callers can import from this component's path.
export { formatTick };
export type { FormatKind };

// ── Types ─────────────────────────────────────────────────────────────────────

export interface TimeSeriesDataPoint {
  [key: string]: string | number | undefined;
}

export interface TimeSeriesDef {
  key: string;
  label: string;
  /** Hex color override — defaults to monochrome series color by index. */
  color?: string;
  type?: "line" | "area";
}

export interface TimeSeriesChartProps {
  /** Array of data objects. Each object must have `xKey` plus one key per series. */
  data: TimeSeriesDataPoint[];
  /** Series definitions. */
  series: TimeSeriesDef[];
  /** Which key in each data point is the X-axis value. */
  xKey: string;
  /** Chart height in pixels. Defaults to 240. */
  height?: number;
  /** Format kind for Y-axis tick labels and tooltip values. */
  format?: FormatKind;
  /** Optional reference/threshold value rendered as a dashed horizontal line. */
  referenceValue?: number;
  /** Accessible label for the chart wrapper. */
  ariaLabel?: string;
  /** Text shown when data is empty — callers supply a translated string. */
  emptyLabel?: string;
}

// ── Custom tooltip ────────────────────────────────────────────────────────────

function MonoTooltip({
  active,
  payload,
  label,
  format: fmt = "number",
}: TooltipProps<ValueType, NameType> & { format?: FormatKind }) {
  if (!active || !payload || payload.length === 0) return null;
  return (
    <div style={CHART_TOOLTIP_STYLE}>
      <p
        style={{
          marginBottom: 4,
          fontWeight: 600,
          fontSize: 11,
          color: "var(--chart-label)",
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
              borderRadius: "50%",
              background: String(entry.color ?? "var(--chart-series-1)"),
              flexShrink: 0,
            }}
          />
          <span style={{ color: "var(--chart-label)", fontSize: 12 }}>{String(entry.name ?? "")}</span>
          <span
            style={{
              marginLeft: "auto",
              fontFamily: "'JetBrains Mono', monospace",
              fontWeight: 600,
              fontSize: 12,
              color: "var(--chart-tooltip-text)",
              paddingLeft: 12,
            }}
          >
            {formatTick(Number(entry.value ?? 0), fmt)}
          </span>
        </div>
      ))}
    </div>
  );
}

// ── Component ─────────────────────────────────────────────────────────────────

/**
 * Multi-series line / area chart — monochrome VinUni admin theme.
 *
 * - Primary series (index 0): ink (#171717).
 * - Secondary/tertiary series: gray ramp.
 * - Optional dashed reference line (neutral gray threshold).
 * - ResponsiveContainer fills 100% of parent width.
 * - role="img" + aria-label for screen readers.
 * - Graceful empty state — no crash when data=[].
 */
export function TimeSeriesChart({
  data,
  series,
  xKey,
  height = 240,
  format: fmt = "number",
  referenceValue,
  ariaLabel = "Time series chart",
  emptyLabel = "No data",
}: TimeSeriesChartProps) {
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
        <ComposedChart
          data={data}
          margin={{ top: 4, right: 8, bottom: 0, left: 0 }}
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
            content={<MonoTooltip format={fmt} />}
            cursor={CHART_TOOLTIP_CURSOR_STYLE}
          />
          <Legend
            wrapperStyle={{ fontSize: 11, color: "var(--chart-label)", paddingTop: 8 }}
            iconType="circle"
            iconSize={8}
          />
          {referenceValue !== undefined && (
            <ReferenceLine
              y={referenceValue}
              stroke={CHART_REFERENCE_COLOR}
              strokeDasharray="4 3"
              label={{
                value: formatTick(referenceValue, fmt),
                position: "insideTopRight",
                fontSize: 10,
                fill: CHART_REFERENCE_COLOR,
              }}
            />
          )}
          {series.map((s, idx) => {
            const color = s.color ?? seriesColor(idx);
            if (s.type === "area") {
              return (
                <Area
                  key={s.key}
                  type={CHART_CURVE_TYPE}
                  dataKey={s.key}
                  name={s.label}
                  stroke={color}
                  strokeWidth={idx === 0 ? 2 : 1.5}
                  fill={color}
                  fillOpacity={0.06}
                  dot={false}
                  activeDot={{ r: 3, strokeWidth: 0 }}
                />
              );
            }
            return (
              <Line
                key={s.key}
                type={CHART_CURVE_TYPE}
                dataKey={s.key}
                name={s.label}
                stroke={color}
                strokeWidth={idx === 0 ? 2 : 1.5}
                dot={false}
                activeDot={{ r: 3, strokeWidth: 0 }}
              />
            );
          })}
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}
