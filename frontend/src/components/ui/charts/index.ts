// ── Pure helpers (safe to import in server/test contexts) ─────────────────────
export {
  formatTick,
  donutTotal,
  sliceColor,
  buildColorScale,
  buildMonochromeScale,
} from "./chart-helpers";
export type { FormatKind, DonutSliceData } from "./chart-helpers";

// ── Chart theme constants ─────────────────────────────────────────────────────
export {
  seriesColor,
  toneColor,
  buildSeverityScale,
  CHART_INK,
  CHART_TEAL,
  CHART_AMBER,
  CHART_RED,
} from "./chart-theme";
export type { ChartTone } from "./chart-theme";

// ── React chart components ("use client") ─────────────────────────────────────
export { TimeSeriesChart } from "./time-series-chart";
export type {
  TimeSeriesChartProps,
  TimeSeriesDataPoint,
  TimeSeriesDef,
} from "./time-series-chart";

export { DonutChart } from "./donut-chart";
export type { DonutChartProps, DonutSlice } from "./donut-chart";

export { StackedBarChart } from "./stacked-bar-chart";
export type {
  StackedBarChartProps,
  StackedBarDataPoint,
  StackedBarSeriesDef,
} from "./stacked-bar-chart";

export { Heatmap } from "./heatmap-chart";
export type { HeatmapProps, HeatmapCell, HeatmapColorScale } from "./heatmap-chart";

export { PercentileBandChart } from "./percentile-band-chart";
export type {
  PercentileBandChartProps,
  PercentileBandDataPoint,
} from "./percentile-band-chart";
