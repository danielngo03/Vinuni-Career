/**
 * Unit tests for the AI chat pipe-table parser.
 *
 * The vitest environment is `node` (no DOM), so we only exercise the pure
 * parsing/analysis helpers. The React rendering lives in `message-bubble.tsx`
 * and is covered by browser/E2E QA.
 */
import { describe, it, expect } from "vitest";
import {
  analyzeColumns,
  parseNumericCell,
  parseTableAt,
  segmentContent,
  shouldRenderBars,
  splitTableRow,
} from "./markdown-table";

/* -------------------------------------------------------------------------- */
/* splitTableRow — safe cell splitting                                        */
/* -------------------------------------------------------------------------- */

describe("splitTableRow", () => {
  it("drops border pipes and trims cells", () => {
    expect(splitTableRow("| Job | Applications |")).toEqual([
      "Job",
      "Applications",
    ]);
  });

  it("supports pipeless (borderless) rows", () => {
    expect(splitTableRow("Job | Applications")).toEqual([
      "Job",
      "Applications",
    ]);
  });

  it("keeps escaped pipes as literal characters", () => {
    expect(splitTableRow("| a \\| b | c |")).toEqual(["a | b", "c"]);
  });
});

/* -------------------------------------------------------------------------- */
/* parseTableAt — header + separator + rows                                   */
/* -------------------------------------------------------------------------- */

describe("parseTableAt", () => {
  const lines = [
    "| Job | Applications |",
    "| --- | --- |",
    "| Backend Intern | 42 |",
    "| Frontend Intern | 17 |",
  ];

  it("parses a well-formed table", () => {
    const result = parseTableAt(lines, 0);
    expect(result).not.toBeNull();
    expect(result?.table.headers).toEqual(["Job", "Applications"]);
    expect(result?.table.rows).toEqual([
      ["Backend Intern", "42"],
      ["Frontend Intern", "17"],
    ]);
    expect(result?.end).toBe(4);
  });

  it("captures separator alignment", () => {
    const aligned = [
      "| Job | Count |",
      "| :--- | ---: |",
      "| A | 1 |",
    ];
    const result = parseTableAt(aligned, 0);
    expect(result?.table.aligns).toEqual(["left", "right"]);
  });

  it("returns null when the separator row is missing", () => {
    const bad = ["| Job | Applications |", "| Backend Intern | 42 |"];
    expect(parseTableAt(bad, 0)).toBeNull();
  });

  it("returns null when separator column count does not match header", () => {
    const bad = ["| A | B | C |", "| --- | --- |", "| 1 | 2 | 3 |"];
    expect(parseTableAt(bad, 0)).toBeNull();
  });

  it("normalises ragged body rows to the header width", () => {
    const ragged = [
      "| A | B | C |",
      "| --- | --- | --- |",
      "| 1 | 2 |",
    ];
    const result = parseTableAt(ragged, 0);
    expect(result?.table.rows).toEqual([["1", "2", ""]]);
  });

  it("accepts a header + separator with no body rows", () => {
    const empty = ["| A | B |", "| --- | --- |"];
    const result = parseTableAt(empty, 0);
    expect(result?.table.rows).toEqual([]);
  });
});

/* -------------------------------------------------------------------------- */
/* segmentContent — mixed prose + table                                       */
/* -------------------------------------------------------------------------- */

describe("segmentContent", () => {
  it("splits prose around a table into ordered blocks", () => {
    const content = [
      "Here are your **top jobs**:",
      "",
      "| Job | Applications |",
      "| --- | --- |",
      "| Backend Intern | 42 |",
      "",
      "Let me know if you want more detail.",
    ].join("\n");
    const blocks = segmentContent(content);
    expect(blocks.map((b) => b.type)).toEqual(["lines", "table", "lines"]);
    const table = blocks[1]!;
    expect(table.type === "table" && table.table.headers).toEqual([
      "Job",
      "Applications",
    ]);
  });

  it("falls back to a single lines block for malformed tables", () => {
    const content = [
      "| Job | Applications |",
      "| Backend Intern | 42 |",
    ].join("\n");
    const blocks = segmentContent(content);
    expect(blocks).toHaveLength(1);
    expect(blocks[0]!.type).toBe("lines");
  });

  it("never throws on empty content", () => {
    expect(() => segmentContent("")).not.toThrow();
  });
});

/* -------------------------------------------------------------------------- */
/* parseNumericCell — numeric detection                                       */
/* -------------------------------------------------------------------------- */

describe("parseNumericCell", () => {
  it("parses plain ints and decimals", () => {
    expect(parseNumericCell("42")).toBe(42);
    expect(parseNumericCell("12.5")).toBe(12.5);
    expect(parseNumericCell("-3")).toBe(-3);
  });

  it("parses percentages and currency-ish values", () => {
    expect(parseNumericCell("42%")).toBe(42);
    expect(parseNumericCell("$1,200")).toBe(1200);
    expect(parseNumericCell("₫3,500")).toBe(3500);
  });

  it("rejects non-numeric and unit-bearing text", () => {
    expect(parseNumericCell("Backend Intern")).toBeNull();
    expect(parseNumericCell("12ms")).toBeNull();
    expect(parseNumericCell("")).toBeNull();
    expect(parseNumericCell("-")).toBeNull();
  });
});

/* -------------------------------------------------------------------------- */
/* analyzeColumns + shouldRenderBars — bar eligibility                        */
/* -------------------------------------------------------------------------- */

describe("analyzeColumns / shouldRenderBars", () => {
  const table = parseTableAt(
    [
      "| Job | Applications |",
      "| --- | --- |",
      "| Backend Intern | 42 |",
      "| Frontend Intern | 17 |",
    ],
    0,
  )!.table;

  it("flags a fully-numeric column and renders bars", () => {
    const stats = analyzeColumns(table);
    expect(stats[0]!.numeric).toBe(false); // Job column is text
    expect(stats[1]!.numeric).toBe(true); // Applications column is numeric
    expect(stats[1]!.max).toBe(42);
    expect(shouldRenderBars(stats[1]!)).toBe(true);
  });

  it("does not render bars for text columns", () => {
    const stats = analyzeColumns(table);
    expect(shouldRenderBars(stats[0]!)).toBe(false);
  });

  it("does not render bars with fewer than two numeric rows", () => {
    const single = parseTableAt(
      ["| Job | Count |", "| --- | --- |", "| Only | 5 |"],
      0,
    )!.table;
    const stats = analyzeColumns(single);
    expect(stats[1]!.numeric).toBe(true);
    expect(shouldRenderBars(stats[1]!)).toBe(false);
  });

  it("does not render bars when the max is not positive", () => {
    const zeros = parseTableAt(
      ["| Job | Count |", "| --- | --- |", "| A | 0 |", "| B | 0 |"],
      0,
    )!.table;
    const stats = analyzeColumns(zeros);
    expect(stats[1]!.numeric).toBe(true);
    expect(stats[1]!.max).toBe(0);
    expect(shouldRenderBars(stats[1]!)).toBe(false);
  });
});
