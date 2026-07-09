"use client";

import * as React from "react";
import {
  ResponsiveContainer,
  AreaChart as RCAreaChart,
  Area,
  LineChart as RCLineChart,
  Line,
  BarChart as RCBarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  PieChart,
  Pie,
  Cell,
  RadialBarChart,
  RadialBar,
  PolarAngleAxis,
  type TooltipProps,
} from "recharts";
import type { NameType, ValueType } from "recharts/types/component/DefaultTooltipContent";
import { cn } from "@/lib/utils";

/* -------------------------------------------------------------------------- */
/* Content data-viz palette (v10, DESIGN.md §1.1.2)                            */
/* -------------------------------------------------------------------------- */

/** Categorical hues in the locked order (colorblind-safe ordering). */
export const VIZ = {
  indigo: "#6366f1",
  teal: "#14b8a6",
  amber: "#f59e0b",
  rose: "#f43f5e",
  sky: "#0ea5e9",
  emerald: "#10b981",
  violet: "#8b5cf6",
  orange: "#f97316",
} as const;

export type VizHue = keyof typeof VIZ;

/** Series colors, in order — use for chart series / categories. */
export const VIZ_SERIES: string[] = [
  VIZ.indigo,
  VIZ.teal,
  VIZ.amber,
  VIZ.rose,
  VIZ.sky,
  VIZ.emerald,
  VIZ.violet,
  VIZ.orange,
];

/** Semantic content colors (NOT the mono shell tokens). */
export const VIZ_SEMANTIC = {
  success: VIZ.emerald,
  warning: VIZ.amber,
  danger: "#c83538", // VinUni red
  info: VIZ.sky,
  ai: VIZ.indigo,
} as const;

export function seriesColor(index: number): string {
  return VIZ_SERIES[index % VIZ_SERIES.length]!;
}

/* Axis / grid read from theme tokens so charts adapt to light/dark. */
const AXIS_TICK = "var(--text-muted)";
const GRID = "var(--border-default)";

/* -------------------------------------------------------------------------- */
/* Shared themed tooltip                                                      */
/* -------------------------------------------------------------------------- */

const TOOLTIP_STYLE: React.CSSProperties = {
  background: "var(--surface-card)",
  border: "1px solid var(--border-default)",
  borderRadius: 10,
  boxShadow: "var(--shadow-md)",
  padding: "8px 12px",
  fontSize: 12,
  color: "var(--text-primary)",
};

function VizTooltip({
  active,
  payload,
  label,
  formatValue,
}: TooltipProps<ValueType, NameType> & { formatValue?: (v: number) => string }) {
  if (!active || !payload || payload.length === 0) return null;
  const fmt = formatValue ?? ((v: number) => new Intl.NumberFormat().format(v));
  return (
    <div style={TOOLTIP_STYLE}>
      {label != null && label !== "" && (
        <p
          style={{
            marginBottom: 4,
            fontWeight: 600,
            fontSize: 11,
            color: "var(--text-muted)",
            letterSpacing: "0.06em",
            textTransform: "uppercase",
          }}
        >
          {String(label)}
        </p>
      )}
      {payload.map((entry, i) => (
        <div
          key={`${String(entry.dataKey ?? entry.name)}-${i}`}
          style={{ display: "flex", alignItems: "center", gap: 6, marginTop: 2 }}
        >
          <span
            style={{
              width: 8,
              height: 8,
              borderRadius: "50%",
              background: String(entry.color ?? VIZ.indigo),
              flexShrink: 0,
            }}
          />
          <span style={{ color: "var(--text-secondary)", fontSize: 12 }}>
            {String(entry.name ?? "")}
          </span>
          <span
            style={{
              marginLeft: "auto",
              fontVariantNumeric: "tabular-nums",
              fontWeight: 600,
              fontSize: 12,
              color: "var(--text-primary)",
              paddingLeft: 16,
            }}
          >
            {fmt(Number(entry.value ?? 0))}
          </span>
        </div>
      ))}
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* Types                                                                      */
/* -------------------------------------------------------------------------- */

export type ChartDatum = Record<string, string | number | null | undefined>;

export interface SeriesDef {
  key: string;
  label: string;
  /** Hex color override; defaults to the categorical palette by index. */
  color?: string;
}

interface XYChartProps {
  data: ChartDatum[];
  series: SeriesDef[];
  xKey: string;
  height?: number;
  formatValue?: (v: number) => string;
  ariaLabel?: string;
  emptyLabel?: string;
  className?: string;
}

function ChartFrame({
  height,
  ariaLabel,
  emptyLabel,
  empty,
  className,
  children,
}: {
  height: number;
  ariaLabel: string;
  emptyLabel: string;
  empty: boolean;
  className?: string;
  children: React.ReactElement;
}) {
  if (empty) {
    return (
      <div
        role="img"
        aria-label={ariaLabel}
        style={{ height }}
        className={cn(
          "flex items-center justify-center rounded-lg border border-dashed border-border text-xs text-muted-foreground",
          className,
        )}
      >
        {emptyLabel}
      </div>
    );
  }
  return (
    <div
      role="img"
      aria-label={ariaLabel}
      style={{ width: "100%", height }}
      className={className}
    >
      <ResponsiveContainer width="100%" height="100%">
        {children}
      </ResponsiveContainer>
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* Area / Line                                                                */
/* -------------------------------------------------------------------------- */

/** Filled area chart (single or multi-series) with soft gradient fills. */
export function AreaChart({
  data,
  series,
  xKey,
  height = 240,
  formatValue,
  ariaLabel = "Area chart",
  emptyLabel = "No data",
  className,
}: XYChartProps) {
  return (
    <ChartFrame
      height={height}
      ariaLabel={ariaLabel}
      emptyLabel={emptyLabel}
      empty={data.length === 0 || series.length === 0}
      className={className}
    >
      <RCAreaChart data={data} margin={{ top: 6, right: 10, bottom: 0, left: 0 }}>
        <defs>
          {series.map((s, i) => {
            const color = s.color ?? seriesColor(i);
            return (
              <linearGradient key={s.key} id={`viz-area-${s.key}`} x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={color} stopOpacity={0.22} />
                <stop offset="100%" stopColor={color} stopOpacity={0.02} />
              </linearGradient>
            );
          })}
        </defs>
        <CartesianGrid strokeDasharray="3 3" stroke={GRID} vertical={false} />
        <XAxis
          dataKey={xKey}
          tick={{ fill: AXIS_TICK, fontSize: 11 }}
          axisLine={{ stroke: GRID }}
          tickLine={false}
          dy={4}
        />
        <YAxis
          tickFormatter={formatValue}
          tick={{ fill: AXIS_TICK, fontSize: 11 }}
          axisLine={false}
          tickLine={false}
          width={44}
        />
        <Tooltip
          content={<VizTooltip formatValue={formatValue} />}
          cursor={{ stroke: GRID, strokeWidth: 1 }}
        />
        {series.map((s, i) => {
          const color = s.color ?? seriesColor(i);
          return (
            <Area
              key={s.key}
              type="monotone"
              dataKey={s.key}
              name={s.label}
              stroke={color}
              strokeWidth={2}
              fill={`url(#viz-area-${s.key})`}
              dot={false}
              activeDot={{ r: 3, strokeWidth: 0 }}
            />
          );
        })}
      </RCAreaChart>
    </ChartFrame>
  );
}

/** Multi-series line chart. */
export function MultiLineChart({
  data,
  series,
  xKey,
  height = 240,
  formatValue,
  ariaLabel = "Line chart",
  emptyLabel = "No data",
  className,
}: XYChartProps) {
  return (
    <ChartFrame
      height={height}
      ariaLabel={ariaLabel}
      emptyLabel={emptyLabel}
      empty={data.length === 0 || series.length === 0}
      className={className}
    >
      <RCLineChart data={data} margin={{ top: 6, right: 10, bottom: 0, left: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke={GRID} vertical={false} />
        <XAxis
          dataKey={xKey}
          tick={{ fill: AXIS_TICK, fontSize: 11 }}
          axisLine={{ stroke: GRID }}
          tickLine={false}
          dy={4}
        />
        <YAxis
          tickFormatter={formatValue}
          tick={{ fill: AXIS_TICK, fontSize: 11 }}
          axisLine={false}
          tickLine={false}
          width={44}
        />
        <Tooltip content={<VizTooltip formatValue={formatValue} />} cursor={{ stroke: GRID }} />
        {series.map((s, i) => {
          const color = s.color ?? seriesColor(i);
          return (
            <Line
              key={s.key}
              type="monotone"
              dataKey={s.key}
              name={s.label}
              stroke={color}
              strokeWidth={2}
              dot={false}
              activeDot={{ r: 3, strokeWidth: 0 }}
            />
          );
        })}
      </RCLineChart>
    </ChartFrame>
  );
}

/** Single-series line chart (thin wrapper over {@link MultiLineChart}). */
export function LineChart(props: XYChartProps) {
  return <MultiLineChart {...props} />;
}

/* -------------------------------------------------------------------------- */
/* Bars                                                                       */
/* -------------------------------------------------------------------------- */

/** Vertical bar chart (single or grouped). */
export function BarChart({
  data,
  series,
  xKey,
  height = 240,
  formatValue,
  ariaLabel = "Bar chart",
  emptyLabel = "No data",
  className,
  stacked = false,
}: XYChartProps & { stacked?: boolean }) {
  return (
    <ChartFrame
      height={height}
      ariaLabel={ariaLabel}
      emptyLabel={emptyLabel}
      empty={data.length === 0 || series.length === 0}
      className={className}
    >
      <RCBarChart data={data} margin={{ top: 6, right: 10, bottom: 0, left: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke={GRID} vertical={false} />
        <XAxis
          dataKey={xKey}
          tick={{ fill: AXIS_TICK, fontSize: 11 }}
          axisLine={{ stroke: GRID }}
          tickLine={false}
          dy={4}
        />
        <YAxis
          tickFormatter={formatValue}
          tick={{ fill: AXIS_TICK, fontSize: 11 }}
          axisLine={false}
          tickLine={false}
          width={44}
        />
        <Tooltip
          content={<VizTooltip formatValue={formatValue} />}
          cursor={{ fill: "var(--bg-subtle)" }}
        />
        {series.map((s, i) => {
          const color = s.color ?? seriesColor(i);
          return (
            <Bar
              key={s.key}
              dataKey={s.key}
              name={s.label}
              fill={color}
              stackId={stacked ? "stack" : undefined}
              radius={stacked ? 0 : [4, 4, 0, 0]}
              maxBarSize={44}
            />
          );
        })}
      </RCBarChart>
    </ChartFrame>
  );
}

/** Stacked bar chart (thin wrapper over {@link BarChart}). */
export function StackedBar(props: XYChartProps) {
  return <BarChart {...props} stacked />;
}

export interface HorizontalBarDatum {
  label: string;
  value: number;
  color?: string;
}

/**
 * Horizontal channel-mix bars — CSS-driven (no chart lib), crisp for source-mix
 * / category breakdowns. Rows: label · colored fill bar · right-aligned value.
 */
export function HorizontalBars({
  data,
  max,
  formatValue,
  className,
  ariaLabel = "Horizontal bar chart",
  emptyLabel = "No data",
}: {
  data: HorizontalBarDatum[];
  max?: number;
  formatValue?: (v: number) => string;
  className?: string;
  ariaLabel?: string;
  emptyLabel?: string;
}) {
  if (data.length === 0) {
    return (
      <div
        role="img"
        aria-label={ariaLabel}
        className="flex h-16 items-center justify-center rounded-lg border border-dashed border-border text-xs text-muted-foreground"
      >
        {emptyLabel}
      </div>
    );
  }
  const fmt = formatValue ?? ((v: number) => new Intl.NumberFormat().format(v));
  const ceiling = max ?? Math.max(...data.map((d) => d.value), 1);
  return (
    <ul role="img" aria-label={ariaLabel} className={cn("space-y-2.5", className)}>
      {data.map((d, i) => {
        const pct = ceiling > 0 ? Math.round((d.value / ceiling) * 100) : 0;
        const color = d.color ?? seriesColor(i);
        return (
          <li key={d.label} className="grid grid-cols-[7rem_1fr_auto] items-center gap-3">
            <span className="type-small truncate text-muted-foreground">{d.label}</span>
            <span className="h-2 overflow-hidden rounded-full bg-[var(--bg-muted)]">
              <span
                className="block h-full rounded-full"
                style={{ width: `${Math.max(pct, d.value > 0 ? 3 : 0)}%`, background: color }}
              />
            </span>
            <span className="w-12 text-right text-[0.8125rem] font-semibold tabular-nums text-foreground">
              {fmt(d.value)}
            </span>
          </li>
        );
      })}
    </ul>
  );
}

/* -------------------------------------------------------------------------- */
/* Funnel                                                                     */
/* -------------------------------------------------------------------------- */

export interface FunnelStage {
  label: string;
  value: number;
  color?: string;
}

/**
 * Recruiting funnel — descending horizontal bars with per-stage value and
 * step-over-step conversion vs the previous stage. CSS-driven for crispness.
 */
export function FunnelChart({
  stages,
  formatValue,
  className,
  ariaLabel = "Funnel chart",
  emptyLabel = "No data",
  conversionLabel = "of previous",
}: {
  stages: FunnelStage[];
  formatValue?: (v: number) => string;
  className?: string;
  ariaLabel?: string;
  emptyLabel?: string;
  conversionLabel?: string;
}) {
  if (stages.length === 0) {
    return (
      <div
        role="img"
        aria-label={ariaLabel}
        className="flex h-24 items-center justify-center rounded-lg border border-dashed border-border text-xs text-muted-foreground"
      >
        {emptyLabel}
      </div>
    );
  }
  const fmt = formatValue ?? ((v: number) => new Intl.NumberFormat().format(v));
  const top = Math.max(stages[0]?.value ?? 0, 1);
  return (
    <ol role="img" aria-label={ariaLabel} className={cn("space-y-2", className)}>
      {stages.map((s, i) => {
        const pct = top > 0 ? Math.round((s.value / top) * 100) : 0;
        const prev = stages[i - 1]?.value;
        const conv = prev && prev > 0 ? Math.round((s.value / prev) * 100) : null;
        const color = s.color ?? seriesColor(i);
        return (
          <li key={s.label}>
            <div className="mb-1 flex items-center justify-between gap-2">
              <span className="type-small font-medium text-foreground">{s.label}</span>
              <span className="flex items-center gap-2">
                <span className="text-[0.8125rem] font-semibold tabular-nums text-foreground">
                  {fmt(s.value)}
                </span>
                {conv != null && (
                  <span className="text-[0.6875rem] font-medium tabular-nums text-muted-foreground">
                    {conv}% {conversionLabel}
                  </span>
                )}
              </span>
            </div>
            <span className="block h-2.5 overflow-hidden rounded-full bg-[var(--bg-muted)]">
              <span
                className="block h-full rounded-full transition-[width] duration-500"
                style={{ width: `${Math.max(pct, s.value > 0 ? 4 : 0)}%`, background: color }}
              />
            </span>
          </li>
        );
      })}
    </ol>
  );
}

/* -------------------------------------------------------------------------- */
/* Donut / Radial                                                             */
/* -------------------------------------------------------------------------- */

export interface DonutSlice {
  label: string;
  value: number;
  color?: string;
}

/** Donut chart with an optional big center metric. */
export function DonutChart({
  data,
  height = 200,
  centerValue,
  centerLabel,
  formatValue,
  ariaLabel = "Donut chart",
  emptyLabel = "No data",
  className,
}: {
  data: DonutSlice[];
  height?: number;
  centerValue?: string;
  centerLabel?: string;
  formatValue?: (v: number) => string;
  ariaLabel?: string;
  emptyLabel?: string;
  className?: string;
}) {
  const total = data.reduce((sum, d) => sum + d.value, 0);
  if (data.length === 0 || total === 0) {
    return (
      <div
        role="img"
        aria-label={ariaLabel}
        style={{ height }}
        className={cn(
          "flex items-center justify-center rounded-lg border border-dashed border-border text-xs text-muted-foreground",
          className,
        )}
      >
        {emptyLabel}
      </div>
    );
  }
  return (
    <div role="img" aria-label={ariaLabel} className={cn("relative", className)} style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <PieChart>
          <Pie
            data={data}
            dataKey="value"
            nameKey="label"
            innerRadius="62%"
            outerRadius="90%"
            paddingAngle={2}
            stroke="var(--surface-card)"
            strokeWidth={2}
          >
            {data.map((d, i) => (
              <Cell key={d.label} fill={d.color ?? seriesColor(i)} />
            ))}
          </Pie>
          <Tooltip content={<VizTooltip formatValue={formatValue} />} />
        </PieChart>
      </ResponsiveContainer>
      {(centerValue != null || centerLabel != null) && (
        <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
          {centerValue != null && (
            <span className="type-metric text-foreground">{centerValue}</span>
          )}
          {centerLabel != null && (
            <span className="type-caption mt-0.5 text-muted-foreground">{centerLabel}</span>
          )}
        </div>
      )}
    </div>
  );
}

/**
 * Radial gauge (single value 0–100) with a big center number — health/score
 * indicator à la Pipeline-OS.
 */
export function RadialChart({
  value,
  height = 200,
  color = VIZ.indigo,
  centerLabel,
  suffix = "%",
  ariaLabel = "Radial gauge",
  className,
}: {
  value: number;
  height?: number;
  color?: string;
  centerLabel?: string;
  suffix?: string;
  ariaLabel?: string;
  className?: string;
}) {
  const clamped = Math.max(0, Math.min(100, Math.round(value)));
  const chartData = [{ name: "value", value: clamped, fill: color }];
  return (
    <div role="img" aria-label={ariaLabel} className={cn("relative", className)} style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <RadialBarChart
          innerRadius="66%"
          outerRadius="100%"
          data={chartData}
          startAngle={90}
          endAngle={-270}
        >
          <PolarAngleAxis type="number" domain={[0, 100]} tick={false} />
          <RadialBar background={{ fill: "var(--bg-muted)" }} dataKey="value" cornerRadius={999} />
        </RadialBarChart>
      </ResponsiveContainer>
      <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
        <span className="type-metric text-foreground">
          {clamped}
          <span className="type-h3 align-top text-muted-foreground">{suffix}</span>
        </span>
        {centerLabel != null && (
          <span className="type-caption mt-0.5 text-muted-foreground">{centerLabel}</span>
        )}
      </div>
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* Sparkline                                                                  */
/* -------------------------------------------------------------------------- */

/** Tiny inline trend line (no axes). Pass raw numbers. */
export function Sparkline({
  data,
  color = VIZ.indigo,
  width = 96,
  height = 28,
  filled = true,
  className,
  ariaLabel = "Trend sparkline",
}: {
  data: number[];
  color?: string;
  width?: number;
  height?: number;
  filled?: boolean;
  className?: string;
  ariaLabel?: string;
}) {
  const gid = React.useId();
  if (data.length < 2) {
    return <span className={cn("inline-block", className)} style={{ width, height }} aria-hidden />;
  }
  const min = Math.min(...data);
  const max = Math.max(...data);
  const range = max - min || 1;
  const stepX = width / (data.length - 1);
  const pts = data.map((v, i) => {
    const x = i * stepX;
    const y = height - 2 - ((v - min) / range) * (height - 4);
    return [x, y] as const;
  });
  const line = pts.map(([x, y], i) => `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`).join(" ");
  const area = `${line} L${width},${height} L0,${height} Z`;
  return (
    <svg
      role="img"
      aria-label={ariaLabel}
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      className={cn("overflow-visible", className)}
    >
      {filled && (
        <>
          <defs>
            <linearGradient id={`spark-${gid}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={color} stopOpacity={0.2} />
              <stop offset="100%" stopColor={color} stopOpacity={0} />
            </linearGradient>
          </defs>
          <path d={area} fill={`url(#spark-${gid})`} />
        </>
      )}
      <path d={line} fill="none" stroke={color} strokeWidth={1.75} strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  );
}

/* -------------------------------------------------------------------------- */
/* Calendar heatmap                                                           */
/* -------------------------------------------------------------------------- */

export interface HeatmapDatum {
  /** ISO date (YYYY-MM-DD). */
  date: string;
  value: number;
}

/**
 * GitHub-style calendar heatmap — value intensity per day over a trailing
 * window, arranged in week columns. Uses the indigo ramp for intensity.
 */
export function CalendarHeatmap({
  data,
  weeks = 16,
  color = VIZ.indigo,
  className,
  ariaLabel = "Activity heatmap",
  emptyLabel = "No activity",
}: {
  data: HeatmapDatum[];
  weeks?: number;
  color?: string;
  className?: string;
  ariaLabel?: string;
  emptyLabel?: string;
}) {
  const byDate = new Map(data.map((d) => [d.date, d.value]));
  const max = Math.max(...data.map((d) => d.value), 1);
  const today = new Date();
  const day = today.getDay();
  // End on the Saturday of the current week; go back `weeks` columns.
  const end = new Date(today);
  end.setDate(today.getDate() + (6 - day));
  const totalDays = weeks * 7;
  const cells: { date: string; value: number }[] = [];
  for (let i = totalDays - 1; i >= 0; i--) {
    const d = new Date(end);
    d.setDate(end.getDate() - i);
    const iso = d.toISOString().slice(0, 10);
    cells.push({ date: iso, value: byDate.get(iso) ?? 0 });
  }
  if (data.length === 0) {
    return (
      <div
        role="img"
        aria-label={ariaLabel}
        className={cn(
          "flex h-24 items-center justify-center rounded-lg border border-dashed border-border text-xs text-muted-foreground",
          className,
        )}
      >
        {emptyLabel}
      </div>
    );
  }
  // Columns of 7 (week) — render as a horizontal flow of week columns.
  const columns: { date: string; value: number }[][] = [];
  for (let w = 0; w < weeks; w++) {
    columns.push(cells.slice(w * 7, w * 7 + 7));
  }
  function intensity(v: number): React.CSSProperties {
    if (v === 0) return { background: "var(--bg-muted)" };
    const t = 0.2 + 0.8 * (v / max);
    return { background: color, opacity: t };
  }
  return (
    <div role="img" aria-label={ariaLabel} className={cn("flex gap-1", className)}>
      {columns.map((col, ci) => (
        <div key={ci} className="flex flex-col gap-1">
          {col.map((cell) => (
            <span
              key={cell.date}
              title={`${cell.date}: ${cell.value}`}
              className="size-2.5 rounded-[3px]"
              style={intensity(cell.value)}
            />
          ))}
        </div>
      ))}
    </div>
  );
}
