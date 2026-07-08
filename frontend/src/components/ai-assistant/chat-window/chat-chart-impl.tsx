"use client";

/**
 * Recharts renderer for `analyze_attachment` chart specs. This module is loaded
 * lazily (see chat-chart.tsx) so Recharts never lands in the main chat bundle.
 *
 * v9 Monochrome: ink for the primary series, then a gray ramp; no decorative
 * hues. Numeric labels are always rendered so meaning never relies on color.
 */

import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  LabelList,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  CHART_AXIS_LINE_COLOR,
  CHART_AXIS_TICK_COLOR,
  CHART_CURVE_TYPE,
  CHART_GRID_COLOR,
  CHART_TOOLTIP_CURSOR_STYLE,
  CHART_TOOLTIP_STYLE,
  seriesColor,
} from "@/components/ui/charts/chart-theme";
import {
  buildCartesianData,
  buildPieSlices,
  formatNumber,
  type AnalysisChart,
} from "./chat-analysis";

const AXIS_TICK = { fontSize: 10, fill: CHART_AXIS_TICK_COLOR } as const;
const LABEL_STYLE = { fontSize: 10, fill: CHART_AXIS_TICK_COLOR } as const;

function labelFormatter(value: unknown): string {
  return formatNumber(Number(value));
}

export function ChatChartImpl({ chart }: { chart: AnalysisChart }) {
  if (chart.type === "pie") {
    return <PieImpl chart={chart} />;
  }
  return <CartesianImpl chart={chart} />;
}

/* -------------------------------- Cartesian ------------------------------- */

function CartesianImpl({ chart }: { chart: AnalysisChart }) {
  const { data, seriesKeys } = buildCartesianData(chart);
  const single = seriesKeys.length === 1;
  const horizontal = chart.type === "bar"; // "bar" = horizontal, "column" = vertical

  if (chart.type === "line") {
    const showLabels = single && data.length <= 8;
    return (
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 12, right: 12, bottom: 4, left: 4 }}>
          <CartesianGrid stroke={CHART_GRID_COLOR} strokeDasharray="3 3" vertical={false} />
          <XAxis
            dataKey="x"
            tick={AXIS_TICK}
            tickLine={false}
            axisLine={{ stroke: CHART_AXIS_LINE_COLOR }}
          />
          <YAxis
            tick={AXIS_TICK}
            tickLine={false}
            axisLine={false}
            width={40}
            tickFormatter={labelFormatter}
          />
          <Tooltip
            contentStyle={CHART_TOOLTIP_STYLE}
            cursor={{ stroke: CHART_GRID_COLOR }}
            formatter={labelFormatter}
          />
          {!single && <Legend wrapperStyle={{ fontSize: 11 }} />}
          {seriesKeys.map((s, i) => (
            <Line
              key={s.key}
              type={CHART_CURVE_TYPE}
              dataKey={s.key}
              name={s.label}
              stroke={seriesColor(i)}
              strokeWidth={2}
              dot={{ r: 2, fill: seriesColor(i) }}
              activeDot={{ r: 4 }}
              isAnimationActive={false}
            >
              {showLabels && (
                <LabelList dataKey={s.key} position="top" formatter={labelFormatter} style={LABEL_STYLE} />
              )}
            </Line>
          ))}
        </LineChart>
      </ResponsiveContainer>
    );
  }

  // bar (horizontal) / column (vertical)
  return (
    <ResponsiveContainer width="100%" height="100%">
      <BarChart
        data={data}
        layout={horizontal ? "vertical" : "horizontal"}
        margin={{ top: 12, right: horizontal ? 28 : 12, bottom: 4, left: 4 }}
      >
        <CartesianGrid stroke={CHART_GRID_COLOR} strokeDasharray="3 3" horizontal={!horizontal} vertical={horizontal} />
        {horizontal ? (
          <>
            <XAxis type="number" tick={AXIS_TICK} tickLine={false} axisLine={false} tickFormatter={labelFormatter} />
            <YAxis
              type="category"
              dataKey="x"
              tick={AXIS_TICK}
              tickLine={false}
              axisLine={{ stroke: CHART_AXIS_LINE_COLOR }}
              width={80}
            />
          </>
        ) : (
          <>
            <XAxis
              dataKey="x"
              type="category"
              tick={AXIS_TICK}
              tickLine={false}
              axisLine={{ stroke: CHART_AXIS_LINE_COLOR }}
            />
            <YAxis type="number" tick={AXIS_TICK} tickLine={false} axisLine={false} width={40} tickFormatter={labelFormatter} />
          </>
        )}
        <Tooltip contentStyle={CHART_TOOLTIP_STYLE} cursor={CHART_TOOLTIP_CURSOR_STYLE} formatter={labelFormatter} />
        {!single && <Legend wrapperStyle={{ fontSize: 11 }} />}
        {seriesKeys.map((s, i) => (
          <Bar key={s.key} dataKey={s.key} name={s.label} fill={seriesColor(i)} radius={horizontal ? [0, 3, 3, 0] : [3, 3, 0, 0]} isAnimationActive={false}>
            {single && (
              <LabelList
                dataKey={s.key}
                position={horizontal ? "right" : "top"}
                formatter={labelFormatter}
                style={LABEL_STYLE}
              />
            )}
          </Bar>
        ))}
      </BarChart>
    </ResponsiveContainer>
  );
}

/* ----------------------------------- Pie ---------------------------------- */

function PieImpl({ chart }: { chart: AnalysisChart }) {
  const slices = buildPieSlices(chart);
  return (
    <ResponsiveContainer width="100%" height="100%">
      <PieChart margin={{ top: 4, right: 4, bottom: 4, left: 4 }}>
        <Pie
          data={slices}
          dataKey="value"
          nameKey="name"
          cx="50%"
          cy="50%"
          outerRadius="72%"
          innerRadius="0%"
          isAnimationActive={false}
          label={(entry: { value?: number }) => formatNumber(Number(entry.value ?? 0))}
          labelLine={false}
          stroke="var(--surface-card)"
          strokeWidth={1}
        >
          {slices.map((_, i) => (
            <Cell key={i} fill={seriesColor(i)} />
          ))}
        </Pie>
        <Tooltip contentStyle={CHART_TOOLTIP_STYLE} formatter={labelFormatter} />
        <Legend wrapperStyle={{ fontSize: 11 }} />
      </PieChart>
    </ResponsiveContainer>
  );
}
