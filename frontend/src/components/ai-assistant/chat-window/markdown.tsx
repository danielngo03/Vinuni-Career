"use client";

import { ArrowUpRight } from "lucide-react";
import { cn } from "@/lib/utils";

/**
 * Lightweight markdown renderer for chat bubbles (no external deps).
 * Supported: paragraphs with preserved blank-line spacing, ## / ### headings,
 * **bold**, *italic*, `inline code`, fenced ``` code blocks, bullet + numbered
 * lists, pipe tables (sticky header, zebra, numeric right-align), horizontal
 * rules, and internal `/path` links.
 */

const TABLE_ROW = /^\s*\|.*\|\s*$/;
const TABLE_SEP = /^\s*\|?[\s:|-]*-[\s:|-]*\|?\s*$/;
const HEADING = /^(#{1,3})\s+(.+)$/;
const BULLET = /^[-•*]\s+(.+)$/;
const NUMBERED = /^(\d+)[.)]\s+(.+)$/;
const FENCE = /^```[\w-]*\s*$/;
const HR = /^-{3,}$/;
const INTERNAL_LINK = /^\/[\w-][^\s]*$/;

/** True when the content contains at least one pipe table (used to widen bubbles). */
export function contentHasTable(content: string): boolean {
  const lines = content.split("\n");
  for (let i = 0; i + 1 < lines.length; i += 1) {
    if (TABLE_ROW.test(lines[i]!.trim()) && TABLE_SEP.test(lines[i + 1]!.trim())) {
      return true;
    }
  }
  return false;
}

type Block =
  | { kind: "code"; text: string }
  | { kind: "table"; header: string; rows: string[] }
  | { kind: "heading"; level: number; text: string }
  | { kind: "bullets"; items: string[] }
  | { kind: "numbered"; items: { n: string; text: string }[] }
  | { kind: "hr" }
  | { kind: "para"; lines: string[] };

function isTableStart(lines: string[], i: number): boolean {
  return (
    TABLE_ROW.test(lines[i]!.trim()) &&
    i + 1 < lines.length &&
    TABLE_SEP.test(lines[i + 1]!.trim())
  );
}

function parseBlocks(content: string): Block[] {
  const lines = content.split("\n");
  const blocks: Block[] = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i]!.trim();
    if (line === "") {
      i += 1;
      continue;
    }

    if (FENCE.test(line)) {
      const body: string[] = [];
      let j = i + 1;
      while (j < lines.length && !FENCE.test(lines[j]!.trim())) {
        body.push(lines[j]!);
        j += 1;
      }
      blocks.push({ kind: "code", text: body.join("\n") });
      i = j + 1;
      continue;
    }

    if (isTableStart(lines, i)) {
      const rows: string[] = [];
      let j = i + 2;
      while (
        j < lines.length &&
        TABLE_ROW.test(lines[j]!.trim()) &&
        !TABLE_SEP.test(lines[j]!.trim())
      ) {
        rows.push(lines[j]!.trim());
        j += 1;
      }
      blocks.push({ kind: "table", header: line, rows });
      i = j;
      continue;
    }

    const heading = line.match(HEADING);
    if (heading) {
      blocks.push({ kind: "heading", level: heading[1]!.length, text: heading[2]! });
      i += 1;
      continue;
    }

    if (HR.test(line)) {
      blocks.push({ kind: "hr" });
      i += 1;
      continue;
    }

    const bullet = line.match(BULLET);
    if (bullet) {
      const items = [bullet[1]!];
      let j = i + 1;
      while (j < lines.length) {
        const m = lines[j]!.trim().match(BULLET);
        if (!m) break;
        items.push(m[1]!);
        j += 1;
      }
      blocks.push({ kind: "bullets", items });
      i = j;
      continue;
    }

    const numbered = line.match(NUMBERED);
    if (numbered) {
      const items = [{ n: numbered[1]!, text: numbered[2]! }];
      let j = i + 1;
      while (j < lines.length) {
        const m = lines[j]!.trim().match(NUMBERED);
        if (!m) break;
        items.push({ n: m[1]!, text: m[2]! });
        j += 1;
      }
      blocks.push({ kind: "numbered", items });
      i = j;
      continue;
    }

    // Paragraph: consecutive plain lines until a blank line or another block start.
    const para = [line];
    let j = i + 1;
    while (j < lines.length) {
      const next = lines[j]!.trim();
      if (
        next === "" ||
        FENCE.test(next) ||
        HEADING.test(next) ||
        HR.test(next) ||
        BULLET.test(next) ||
        NUMBERED.test(next) ||
        isTableStart(lines, j)
      ) {
        break;
      }
      para.push(next);
      j += 1;
    }
    blocks.push({ kind: "para", lines: para });
    i = j;
  }
  return blocks;
}

/** Render markdown-ish chat content. `constrainText` caps prose blocks at ~72ch
 * (fullscreen wide bubbles) while tables/code keep the full width. */
export function FormattedContent({
  content,
  isUser,
  constrainText = false,
}: {
  content: string;
  isUser: boolean;
  constrainText?: boolean;
}) {
  const blocks = parseBlocks(content);
  const textCap = constrainText ? "max-w-[72ch]" : undefined;
  return (
    <div className="space-y-3">
      {blocks.map((block, i) => {
        switch (block.kind) {
          case "code":
            return <CodeBlock key={i} text={block.text} isUser={isUser} />;
          case "table":
            return (
              <MarkdownTable key={i} header={block.header} rows={block.rows} isUser={isUser} />
            );
          case "heading":
            return (
              <p
                key={i}
                className={cn(
                  block.level <= 2 ? "type-h3" : "type-body font-semibold",
                  // Extra breathing room above a heading that follows other
                  // content, so sections don't visually collide.
                  i > 0 && "pt-2",
                  textCap,
                )}
              >
                {renderInline(block.text, isUser)}
              </p>
            );
          case "hr":
            return (
              <hr
                key={i}
                className={cn(
                  "border-t",
                  isUser ? "border-[var(--text-inverted)]/25" : "border-[var(--border-subtle)]",
                )}
              />
            );
          case "bullets":
            return (
              <ul key={i} className={cn("space-y-1", textCap)}>
                {block.items.map((item, j) => (
                  <li key={j} className="flex gap-1.5 pl-1">
                    <span aria-hidden className="select-none opacity-50">
                      •
                    </span>
                    <span className="min-w-0 flex-1">{renderInline(item, isUser)}</span>
                  </li>
                ))}
              </ul>
            );
          case "numbered":
            return (
              <ol key={i} className={cn("space-y-1", textCap)}>
                {block.items.map((item, j) => (
                  <li key={j} className="flex gap-1.5 pl-1">
                    <span className="select-none font-medium tabular-nums opacity-60">
                      {item.n}.
                    </span>
                    <span className="min-w-0 flex-1">{renderInline(item.text, isUser)}</span>
                  </li>
                ))}
              </ol>
            );
          case "para":
            return (
              <div key={i} className={cn("space-y-0.5", textCap)}>
                {block.lines.map((ln, j) => renderParaLine(ln, j, isUser))}
              </div>
            );
        }
      })}
    </div>
  );
}

function renderParaLine(line: string, key: number, isUser: boolean): React.ReactNode {
  if (INTERNAL_LINK.test(line)) {
    return (
      <a
        key={key}
        href={line}
        className={cn(
          "type-caption flex items-center gap-1 font-medium underline underline-offset-2",
          isUser ? "text-[var(--text-inverted)]/90" : "text-[var(--content-ai)]",
        )}
      >
        {line}
        <ArrowUpRight aria-hidden strokeWidth={1.9} className="size-3 shrink-0" />
      </a>
    );
  }
  return (
    <p key={key} className="leading-relaxed">
      {renderInline(line, isUser)}
    </p>
  );
}

function CodeBlock({ text, isUser }: { text: string; isUser: boolean }) {
  return (
    <pre
      className={cn(
        "overflow-x-auto rounded-lg p-3 [scrollbar-width:thin]",
        isUser
          ? "bg-[var(--text-inverted)]/10"
          : "border border-[var(--border-subtle)] bg-[var(--bg-muted)]",
      )}
    >
      <code className="type-caption block whitespace-pre font-mono font-normal leading-relaxed">
        {text}
      </code>
    </pre>
  );
}

function parseCells(row: string): string[] {
  return row
    .trim()
    .replace(/^\|/, "")
    .replace(/\|$/, "")
    .split("|")
    .map((c) => c.trim());
}

/** Numeric-ish cell (numbers, %, currency) — drives per-column right alignment. */
function isNumericish(cell: string): boolean {
  const t = cell.replace(/\*\*/g, "").trim();
  if (t === "" || !/\d/.test(t)) return false;
  return /^[+\-−~≈]?[\d.,\s]+(%|đ|₫|vnd|vnđ|usd)?$/i.test(t);
}

export function MarkdownTable({
  header,
  rows,
  isUser,
}: {
  header: string;
  rows: string[];
  isUser: boolean;
}) {
  const headers = parseCells(header);
  const body = rows.map(parseCells);
  const numericCols = headers.map((_, ci) => {
    const cells = body.map((r) => r[ci] ?? "").filter((c) => c.trim() !== "");
    if (cells.length === 0) return false;
    return cells.filter(isNumericish).length / cells.length >= 0.6;
  });
  return (
    // `min-w` lets columns keep real breathing room in a narrow panel (they scroll
    // horizontally instead of collapsing); the panel is roomy so this rarely triggers.
    <div className="my-1 max-h-[440px] w-full overflow-auto overscroll-contain rounded-lg border border-[var(--border-default)] [scrollbar-width:thin]">
      <table className="type-small w-full min-w-[28rem] border-collapse">
        <thead>
          <tr>
            {headers.map((h, i) => (
              <th
                key={i}
                className={cn(
                  "sticky top-0 z-[1] whitespace-nowrap bg-[var(--bg-muted)] px-3.5 py-2.5 font-semibold text-[var(--text-primary)] shadow-[inset_0_-1px_0_var(--border-default)]",
                  numericCols[i] ? "text-right" : "text-left",
                )}
              >
                {renderInline(h, isUser)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {body.map((r, ri) => (
            <tr key={ri} className="even:bg-[var(--bg-subtle)] [&:last-child>td]:border-b-0">
              {r.map((c, ci) => (
                <td
                  key={ci}
                  className={cn(
                    "border-b border-[var(--border-subtle)] px-3.5 py-2.5 align-top font-normal leading-relaxed text-[var(--text-secondary)]",
                    numericCols[ci] ? "whitespace-nowrap text-right tabular-nums" : "[overflow-wrap:anywhere]",
                  )}
                >
                  {renderInline(c, isUser)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** Inline rendering: `code`, **bold**, *italic*. */
export function renderInline(text: string, isUser: boolean): React.ReactNode {
  const segments = text.split(/(`[^`\n]+`)/g);
  if (segments.length === 1) return renderEmphasis(text, isUser);
  return segments.map((seg, i) => {
    if (seg.startsWith("`") && seg.endsWith("`") && seg.length > 2) {
      return (
        <code
          key={i}
          className={cn(
            "rounded px-1 py-0.5 font-mono text-[0.85em]",
            isUser
              ? "bg-[var(--text-inverted)]/15"
              : "bg-[var(--bg-muted)] text-[var(--text-primary)]",
          )}
        >
          {seg.slice(1, -1)}
        </code>
      );
    }
    return <span key={i}>{renderEmphasis(seg, isUser)}</span>;
  });
}

function renderEmphasis(text: string, isUser: boolean): React.ReactNode {
  const parts = text.split(/(\*\*[^*]+\*\*|\*[^*\s][^*]*\*)/g);
  if (parts.length === 1) return text;
  return parts.map((part, i) => {
    if (part.startsWith("**") && part.endsWith("**") && part.length > 4) {
      return (
        <strong
          key={i}
          className={isUser ? "font-bold text-[var(--text-inverted)]" : "font-semibold"}
        >
          {part.slice(2, -2)}
        </strong>
      );
    }
    if (part.startsWith("*") && part.endsWith("*") && part.length > 2) {
      return <em key={i}>{part.slice(1, -1)}</em>;
    }
    return part;
  });
}
