/**
 * Unit tests for the `analyze_attachment` result parser + chart shaping.
 *
 * The vitest environment is `node` (no DOM), so we only exercise the pure
 * parsing/shaping helpers. React rendering (chat-chart, attachment-analysis)
 * is covered by browser/E2E QA.
 */
import { describe, it, expect } from "vitest";
import {
  buildCartesianData,
  buildPieSlices,
  chartToTable,
  formatNumber,
  hasBody,
  isAnalyzed,
  parseAnalysis,
  type AnalysisChart,
} from "./chat-analysis";

/* -------------------------------------------------------------------------- */
/* parseAnalysis                                                              */
/* -------------------------------------------------------------------------- */

describe("parseAnalysis", () => {
  it("returns null for non-analyze tool results", () => {
    expect(parseAnalysis(null)).toBeNull();
    expect(parseAnalysis(undefined)).toBeNull();
    expect(parseAnalysis({ ok: true, jobs: [] })).toBeNull();
    // Missing the boolean `analyzed` signal.
    expect(parseAnalysis({ status: "analyzed", tables: [] })).toBeNull();
  });

  it("parses a full analyzed result with tables and charts", () => {
    const raw = {
      ok: true,
      status: "analyzed",
      kind: "csv",
      analyzed: true,
      degraded: false,
      summary: "Application volume by department.",
      insights: ["Total: 120", "Peak: CS (48)"],
      tables: [
        {
          title: "Applications",
          columns: ["Department", "Applications"],
          rows: [
            ["CS", "48"],
            ["EE", "30"],
          ],
        },
      ],
      charts: [
        {
          type: "column",
          title: "Applications by department",
          x_label: "Department",
          y_label: "Applications",
          series: [
            {
              label: "Applications",
              points: [
                { x: "CS", y: 48 },
                { x: "EE", y: 30 },
              ],
            },
          ],
        },
      ],
      cached: false,
    };
    const a = parseAnalysis(raw);
    expect(a).not.toBeNull();
    expect(isAnalyzed(a!)).toBe(true);
    expect(hasBody(a!)).toBe(true);
    expect(a!.tables).toHaveLength(1);
    expect(a!.tables[0]!.rows).toEqual([
      ["CS", "48"],
      ["EE", "30"],
    ]);
    expect(a!.charts).toHaveLength(1);
    expect(a!.charts[0]!.type).toBe("column");
  });

  it("represents a couldn't-analyze result honestly", () => {
    const a = parseAnalysis({
      status: "not_analyzable",
      kind: "unknown",
      analyzed: false,
      degraded: false,
      summary: "",
      insights: [],
      tables: [],
      charts: [],
    });
    expect(a).not.toBeNull();
    expect(isAnalyzed(a!)).toBe(false);
    expect(hasBody(a!)).toBe(false);
  });

  it("carries the degraded flag", () => {
    const a = parseAnalysis({
      status: "analyzed",
      analyzed: true,
      degraded: true,
      summary: "ok",
      insights: [],
      tables: [],
      charts: [],
    });
    expect(a!.degraded).toBe(true);
  });

  it("drops malformed tables/charts without throwing", () => {
    const a = parseAnalysis({
      analyzed: true,
      status: "analyzed",
      summary: "",
      insights: [],
      tables: [{ columns: [] }, { columns: ["A"], rows: "nope" }, 42],
      charts: [
        { type: "wat", series: [] },
        { type: "bar", series: [{ points: [{ x: "a" }] }] }, // no numeric y
      ],
    });
    expect(a).not.toBeNull();
    // Empty-columns table dropped; the second yields one column, zero rows.
    expect(a!.tables).toEqual([{ title: "", columns: ["A"], rows: [] }]);
    // Unknown type dropped; the bar chart has no valid points → dropped.
    expect(a!.charts).toEqual([]);
  });

  it("normalises ragged table rows to the column width", () => {
    const a = parseAnalysis({
      analyzed: true,
      status: "analyzed",
      summary: "",
      insights: [],
      tables: [{ columns: ["A", "B", "C"], rows: [["1", "2"]] }],
      charts: [],
    });
    expect(a!.tables[0]!.rows).toEqual([["1", "2", ""]]);
  });
});

/* -------------------------------------------------------------------------- */
/* buildCartesianData                                                        */
/* -------------------------------------------------------------------------- */

const columnChart: AnalysisChart = {
  type: "column",
  title: "t",
  xLabel: "Dept",
  yLabel: "Apps",
  series: [
    { label: "2025", points: [{ x: "CS", y: 10 }, { x: "EE", y: 5 }] },
    { label: "2026", points: [{ x: "CS", y: 12 }, { x: "EE", y: 8 }] },
  ],
};

describe("buildCartesianData", () => {
  it("merges multiple series into rows keyed by x", () => {
    const { data, seriesKeys } = buildCartesianData(columnChart);
    expect(seriesKeys.map((s) => s.key)).toEqual(["2025", "2026"]);
    expect(data).toEqual([
      { x: "CS", "2025": 10, "2026": 12 },
      { x: "EE", "2025": 5, "2026": 8 },
    ]);
  });

  it("de-duplicates colliding series labels", () => {
    const dup: AnalysisChart = {
      ...columnChart,
      series: [
        { label: "Count", points: [{ x: "A", y: 1 }] },
        { label: "Count", points: [{ x: "A", y: 2 }] },
      ],
    };
    const { seriesKeys, data } = buildCartesianData(dup);
    expect(seriesKeys.map((s) => s.key)).toEqual(["Count", "Count (2)"]);
    expect(data).toEqual([{ x: "A", Count: 1, "Count (2)": 2 }]);
  });
});

/* -------------------------------------------------------------------------- */
/* buildPieSlices + chartToTable + formatNumber                              */
/* -------------------------------------------------------------------------- */

describe("buildPieSlices", () => {
  it("flattens the first series into name/value slices", () => {
    const pie: AnalysisChart = {
      type: "pie",
      title: "t",
      xLabel: "",
      yLabel: "",
      series: [{ label: "s", points: [{ x: "Approved", y: 30 }, { x: "Pending", y: 12 }] }],
    };
    expect(buildPieSlices(pie)).toEqual([
      { name: "Approved", value: 30 },
      { name: "Pending", value: 12 },
    ]);
  });
});

describe("chartToTable", () => {
  it("builds a screen-reader table for a cartesian chart", () => {
    const { columns, rows } = chartToTable(columnChart);
    expect(columns).toEqual(["Dept", "2025", "2026"]);
    expect(rows).toEqual([
      ["CS", "10", "12"],
      ["EE", "5", "8"],
    ]);
  });
});

describe("formatNumber", () => {
  it("formats integers and decimals, guards non-finite", () => {
    expect(formatNumber(1200)).toBe("1,200");
    expect(formatNumber(3.14159)).toBe("3.14");
    expect(formatNumber(NaN)).toBe("—");
  });
});
