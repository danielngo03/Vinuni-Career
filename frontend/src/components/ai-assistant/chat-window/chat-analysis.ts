/**
 * Pure, dependency-free parsing + shaping for the `analyze_attachment` tool
 * result rendered in the AI assistant chat.
 *
 * Design goals (mirror markdown-table.ts):
 * - Pure functions only (no React, no DOM, no Recharts) so they are
 *   unit-testable in the `node` vitest environment and reused by the renderer.
 * - Defensive: the wire payload arrives as a loose `Record<string, unknown>`
 *   (a message's `tool_result`). Every accessor coerces/validates and never
 *   throws on malformed/partial input.
 * - Leakage-safe by construction: only the whitelisted, user-safe fields are
 *   read. Provider/model/token/storage internals are never surfaced.
 *
 * Backend contract (P3c `analyze_attachment`):
 *   { ok, status, kind, analyzed, degraded, summary, insights: string[],
 *     tables: [{ title, columns: string[], rows: string[][] }],
 *     charts: [{ type: "bar"|"column"|"line"|"pie", title,
 *                series: [{ label, points: [{ x, y: number }] }],
 *                x_label, y_label }],
 *     cached }
 */

export type ChartType = "bar" | "column" | "line" | "pie";

export interface AnalysisChartPoint {
  x: string;
  y: number;
}

export interface AnalysisChartSeries {
  label: string;
  points: AnalysisChartPoint[];
}

export interface AnalysisChart {
  type: ChartType;
  title: string;
  series: AnalysisChartSeries[];
  xLabel: string;
  yLabel: string;
}

export interface AnalysisTable {
  title: string;
  columns: string[];
  rows: string[][];
}

export interface AttachmentAnalysis {
  status: string;
  kind: string;
  analyzed: boolean;
  degraded: boolean;
  summary: string;
  insights: string[];
  tables: AnalysisTable[];
  charts: AnalysisChart[];
}

const CHART_TYPES: ReadonlySet<string> = new Set([
  "bar",
  "column",
  "line",
  "pie",
]);

function asString(value: unknown): string {
  if (typeof value === "string") return value;
  if (typeof value === "number" && Number.isFinite(value)) return String(value);
  return "";
}

function asBool(value: unknown): boolean {
  return value === true;
}

function asFiniteNumber(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && value.trim() !== "") {
    const n = Number(value);
    if (Number.isFinite(n)) return n;
  }
  return null;
}

function asStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  const out: string[] = [];
  for (const item of value) {
    const s = asString(item).trim();
    if (s) out.push(s);
  }
  return out;
}

function parseTable(value: unknown): AnalysisTable | null {
  if (!value || typeof value !== "object") return null;
  const raw = value as Record<string, unknown>;
  const columns = Array.isArray(raw.columns) ? raw.columns.map(asString) : [];
  if (columns.length === 0) return null;
  const rawRows = Array.isArray(raw.rows) ? raw.rows : [];
  const rows: string[][] = [];
  for (const r of rawRows) {
    if (!Array.isArray(r)) continue;
    // Normalise ragged rows to the column width so rendering stays rectangular.
    rows.push(columns.map((_, c) => asString(r[c])));
  }
  return { title: asString(raw.title), columns, rows };
}

function parsePoint(value: unknown): AnalysisChartPoint | null {
  if (!value || typeof value !== "object") return null;
  const raw = value as Record<string, unknown>;
  const y = asFiniteNumber(raw.y);
  if (y === null) return null;
  return { x: asString(raw.x), y };
}

function parseSeries(value: unknown): AnalysisChartSeries | null {
  if (!value || typeof value !== "object") return null;
  const raw = value as Record<string, unknown>;
  const points: AnalysisChartPoint[] = [];
  if (Array.isArray(raw.points)) {
    for (const p of raw.points) {
      const point = parsePoint(p);
      if (point) points.push(point);
    }
  }
  if (points.length === 0) return null;
  return { label: asString(raw.label), points };
}

function parseChart(value: unknown): AnalysisChart | null {
  if (!value || typeof value !== "object") return null;
  const raw = value as Record<string, unknown>;
  const type = asString(raw.type).toLowerCase();
  if (!CHART_TYPES.has(type)) return null;
  const series: AnalysisChartSeries[] = [];
  if (Array.isArray(raw.series)) {
    for (const s of raw.series) {
      const parsed = parseSeries(s);
      if (parsed) series.push(parsed);
    }
  }
  if (series.length === 0) return null;
  return {
    type: type as ChartType,
    title: asString(raw.title),
    series,
    xLabel: asString(raw.x_label),
    yLabel: asString(raw.y_label),
  };
}

/**
 * Parse a message's loose `tool_result` into a typed, render-ready analysis, or
 * `null` when the payload is not an `analyze_attachment` result. The unique
 * signal is a boolean `analyzed` field (only this tool returns it), so other
 * tools' results are never mistaken for an attachment analysis.
 */
export function parseAnalysis(
  raw: Record<string, unknown> | null | undefined,
): AttachmentAnalysis | null {
  if (!raw || typeof raw !== "object") return null;
  if (typeof raw.analyzed !== "boolean") return null;

  const tables: AnalysisTable[] = [];
  if (Array.isArray(raw.tables)) {
    for (const t of raw.tables) {
      const parsed = parseTable(t);
      if (parsed) tables.push(parsed);
    }
  }
  const charts: AnalysisChart[] = [];
  if (Array.isArray(raw.charts)) {
    for (const c of raw.charts) {
      const parsed = parseChart(c);
      if (parsed) charts.push(parsed);
    }
  }

  return {
    status: asString(raw.status) || (raw.analyzed ? "analyzed" : "not_analyzable"),
    kind: asString(raw.kind) || "unknown",
    analyzed: asBool(raw.analyzed),
    degraded: asBool(raw.degraded),
    summary: asString(raw.summary),
    insights: asStringArray(raw.insights),
    tables,
    charts,
  };
}

/** Whether the analysis succeeded and should render its rich body. */
export function isAnalyzed(a: AttachmentAnalysis): boolean {
  return a.analyzed && a.status === "analyzed";
}

/** Whether there is any visible content (summary/insights/tables/charts). */
export function hasBody(a: AttachmentAnalysis): boolean {
  return (
    a.summary.trim() !== "" ||
    a.insights.length > 0 ||
    a.tables.length > 0 ||
    a.charts.length > 0
  );
}

/* --------------------------------------------------------------------------- */
/* Chart shaping (pure) — consumed by the code-split Recharts renderer.        */
/* --------------------------------------------------------------------------- */

export interface SeriesKey {
  key: string;
  label: string;
}

export interface CartesianData {
  /** One row per x category: `{ x, [seriesKey]: y, ... }`. */
  data: Array<Record<string, string | number>>;
  seriesKeys: SeriesKey[];
}

/**
 * Merge a chart's series into recharts-friendly rows keyed by the x category.
 * Series keys are de-duplicated (`Series`, `Series (2)`, …) so two series that
 * share a label never collide into one column.
 */
export function buildCartesianData(chart: AnalysisChart): CartesianData {
  const seriesKeys: SeriesKey[] = [];
  const usedKeys = new Set<string>();
  chart.series.forEach((s, i) => {
    const label = s.label.trim() || `${i + 1}`;
    let key = label;
    let n = 2;
    while (usedKeys.has(key)) {
      key = `${label} (${n})`;
      n += 1;
    }
    usedKeys.add(key);
    seriesKeys.push({ key, label });
  });

  // Preserve x-order of first appearance across all series.
  const order: string[] = [];
  const rowByX = new Map<string, Record<string, string | number>>();
  chart.series.forEach((s, si) => {
    const seriesKey = seriesKeys[si]?.key ?? String(si);
    for (const p of s.points) {
      const x = p.x || "—";
      let row = rowByX.get(x);
      if (!row) {
        row = { x };
        rowByX.set(x, row);
        order.push(x);
      }
      row[seriesKey] = p.y;
    }
  });

  return { data: order.map((x) => rowByX.get(x)!), seriesKeys };
}

export interface PieSlice {
  name: string;
  value: number;
}

/** Flatten a pie chart's first series into `{ name, value }` slices. */
export function buildPieSlices(chart: AnalysisChart): PieSlice[] {
  const series = chart.series[0];
  if (!series) return [];
  return series.points.map((p, i) => ({
    name: p.x || `${i + 1}`,
    value: p.y,
  }));
}

/**
 * Flatten any chart into a plain `{ columns, rows }` table used for the
 * screen-reader data-table fallback (color is never the only signal).
 */
export function chartToTable(chart: AnalysisChart): {
  columns: string[];
  rows: string[][];
} {
  const xHeader = chart.xLabel.trim() || "";
  if (chart.type === "pie") {
    const slices = buildPieSlices(chart);
    return {
      columns: [xHeader || "", chart.yLabel.trim() || ""],
      rows: slices.map((s) => [s.name, formatNumber(s.value)]),
    };
  }
  const { data, seriesKeys } = buildCartesianData(chart);
  const columns = [xHeader, ...seriesKeys.map((s) => s.label)];
  const rows = data.map((row) => [
    String(row.x ?? ""),
    ...seriesKeys.map((s) => {
      const v = row[s.key];
      return typeof v === "number" ? formatNumber(v) : "";
    }),
  ]);
  return { columns, rows };
}

/** Compact, locale-stable number formatting for labels/fallbacks. */
export function formatNumber(value: number): string {
  if (!Number.isFinite(value)) return "—";
  if (Number.isInteger(value)) return value.toLocaleString("en-US");
  return value.toLocaleString("en-US", { maximumFractionDigits: 2 });
}
