/**
 * Safe, dependency-free parser for GitHub-Flavored-Markdown pipe tables used by
 * the AI assistant chat renderer.
 *
 * Design goals:
 * - Pure functions only (no React, no DOM) so they are unit-testable in the
 *   `node` vitest environment and reused by the message bubble renderer.
 * - No HTML injection: this module never produces HTML strings. It returns
 *   plain data structures (strings/numbers). The renderer builds React elements
 *   from these, and React escapes every text node.
 * - Graceful degradation: anything that is not a well-formed pipe table returns
 *   `null` / falls back to plain-line rendering. Malformed input never throws.
 *
 * A pipe table is:
 *   | Job            | Applications |
 *   | -------------- | ------------ |
 *   | Backend Intern | 42           |
 *
 * i.e. a header row, a GFM separator row (`---`, optionally `:` aligned), then
 * one or more body rows. Leading/trailing pipes are optional (GFM).
 */

export type ColumnAlign = "left" | "right" | "center" | null;

export interface ParsedTable {
  headers: string[];
  rows: string[][];
  /** Explicit alignment from the separator row, per column. */
  aligns: ColumnAlign[];
}

export interface ColumnStat {
  /** True when every body cell in the column parses to a finite number. */
  numeric: boolean;
  /** Parsed numeric values (null when a cell is not numeric). */
  values: Array<number | null>;
  /** Max of the parsed values (0 when no positive value). */
  max: number;
}

/** A segment of assistant content: either raw text lines or a parsed table. */
export type ContentBlock =
  | { type: "lines"; lines: string[] }
  | { type: "table"; table: ParsedTable };

/**
 * Split one table row into trimmed cells, honouring escaped pipes (`\|`).
 * Leading/trailing border pipes are dropped so `| a | b |` -> ["a", "b"].
 */
export function splitTableRow(row: string): string[] {
  const trimmed = row.trim();
  const cells: string[] = [];
  let buf = "";
  for (let i = 0; i < trimmed.length; i += 1) {
    const ch = trimmed[i];
    if (ch === "\\" && trimmed[i + 1] === "|") {
      // Escaped pipe -> literal '|' inside the cell.
      buf += "|";
      i += 1;
      continue;
    }
    if (ch === "|") {
      cells.push(buf);
      buf = "";
      continue;
    }
    buf += ch;
  }
  cells.push(buf);

  // Drop the empty cell produced by a leading/trailing border pipe (GFM allows
  // the outer pipes to be optional).
  if (trimmed.startsWith("|")) cells.shift();
  if (trimmed.endsWith("|") && !trimmed.endsWith("\\|")) cells.pop();

  return cells.map((c) => c.trim());
}

/** A line "looks like" a table row when it contains an unescaped pipe. */
export function looksLikeTableRow(line: string): boolean {
  if (!line.trim()) return false;
  return /(^|[^\\])\|/.test(line);
}

/** GFM separator cell: optional leading/trailing `:` around one or more `-`. */
function isSeparatorCell(cell: string): boolean {
  return /^:?-+:?$/.test(cell.trim());
}

function alignOf(cell: string): ColumnAlign {
  const c = cell.trim();
  const left = c.startsWith(":");
  const right = c.endsWith(":");
  if (left && right) return "center";
  if (right) return "right";
  if (left) return "left";
  return null;
}

/**
 * Attempt to parse a pipe table starting at `lines[start]`.
 * Returns the parsed table and the index of the first line *after* the table,
 * or `null` when there is no well-formed table at `start`.
 */
export function parseTableAt(
  lines: string[],
  start: number,
): { table: ParsedTable; end: number } | null {
  const headerLine = lines[start];
  const separatorLine = lines[start + 1];
  if (headerLine === undefined || separatorLine === undefined) return null;
  if (!looksLikeTableRow(headerLine) || !looksLikeTableRow(separatorLine)) {
    return null;
  }

  const headers = splitTableRow(headerLine);
  const separatorCells = splitTableRow(separatorLine);
  if (headers.length === 0 || separatorCells.length === 0) return null;
  // Every separator cell must be a valid GFM separator, and the column count
  // must match the header. This is the signal that distinguishes a real table
  // from an ordinary line that merely contains a pipe character.
  if (separatorCells.length !== headers.length) return null;
  if (!separatorCells.every(isSeparatorCell)) return null;

  const aligns = separatorCells.map(alignOf);

  const rows: string[][] = [];
  let i = start + 2;
  for (; i < lines.length; i += 1) {
    const line = lines[i];
    if (line === undefined || !looksLikeTableRow(line)) break;
    const cells = splitTableRow(line);
    // Normalise ragged rows to the header width so rendering stays rectangular.
    const normalised = headers.map((_, c) => cells[c] ?? "");
    rows.push(normalised);
  }

  // A table with a header + separator but no body rows is still a valid table.
  return { table: { headers, rows, aligns }, end: i };
}

/**
 * Parse a numeric-ish cell into a finite number, or null.
 * Accepts plain ints/decimals plus common decorations: thousands separators,
 * a leading currency symbol/sign, and a trailing percent sign.
 * Examples: "42" -> 42, "42%" -> 42, "$1,200" -> 1200, "-3.5" -> -3.5.
 */
export function parseNumericCell(cell: string): number | null {
  const raw = cell.trim();
  if (!raw) return null;
  // Must contain at least one digit.
  if (!/\d/.test(raw)) return null;
  // Reject anything that has letters (units like "12ms", "3 apps") — keep the
  // "all numeric column" signal strict so bars only appear on real metrics.
  if (/[a-z]/i.test(raw)) return null;
  // Strip currency symbols, thousands separators, percent, and spaces.
  const cleaned = raw.replace(/[$€£¥₫%\s,]/g, "");
  if (!cleaned || cleaned === "-" || cleaned === "+") return null;
  if (!/^[+-]?\d*\.?\d+$/.test(cleaned)) return null;
  const n = Number(cleaned);
  return Number.isFinite(n) ? n : null;
}

/** Per-column numeric analysis used to decide right-align + bar rendering. */
export function analyzeColumns(table: ParsedTable): ColumnStat[] {
  const colCount = table.headers.length;
  const stats: ColumnStat[] = [];
  for (let c = 0; c < colCount; c += 1) {
    const values = table.rows.map((row) => parseNumericCell(row[c] ?? ""));
    const numeric =
      table.rows.length > 0 && values.every((v) => v !== null);
    const positives = values.filter((v): v is number => v !== null);
    const max = positives.length ? Math.max(...positives, 0) : 0;
    stats.push({ numeric, values, max });
  }
  return stats;
}

/**
 * Whether a numeric column should get inline bars: it must be fully numeric,
 * have at least two rows, and a positive max (so a bar has meaning).
 */
export function shouldRenderBars(stat: ColumnStat): boolean {
  const numericCount = stat.values.filter((v) => v !== null).length;
  return stat.numeric && numericCount >= 2 && stat.max > 0;
}

/**
 * Segment assistant content into ordered blocks of plain lines and tables.
 * Non-table content is preserved verbatim (empty lines kept) so the existing
 * line renderer can apply its own filtering/formatting.
 */
export function segmentContent(content: string): ContentBlock[] {
  const lines = content.replace(/\r\n/g, "\n").split("\n");
  const blocks: ContentBlock[] = [];
  let buffer: string[] = [];

  const flush = () => {
    if (buffer.length) {
      blocks.push({ type: "lines", lines: buffer });
      buffer = [];
    }
  };

  let i = 0;
  while (i < lines.length) {
    const parsed = parseTableAt(lines, i);
    if (parsed) {
      flush();
      blocks.push({ type: "table", table: parsed.table });
      i = parsed.end;
      continue;
    }
    buffer.push(lines[i] ?? "");
    i += 1;
  }
  flush();
  return blocks;
}
