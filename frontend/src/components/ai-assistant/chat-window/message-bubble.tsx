"use client";

import { useState } from "react";
import {
  ArrowSquareOut,
  DownloadSimple,
  Lightning,
  MagnifyingGlass,
  Paperclip,
  Sparkle,
  Spinner,
} from "@phosphor-icons/react";
import { cn } from "@/lib/utils";
import { env } from "@/lib/env";
import type { ChatMessage } from "@/lib/api";
import { getAccessToken } from "@/lib/api/session";
import { TOOL_LABELS, extractAttachmentRefs } from "./constants";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

/** A chart spec the backend emits for the FE to render with Recharts. */
type ChartSpec = {
  type?: string;
  title?: string;
  x_key?: string;
  series?: { key: string; name?: string }[];
  data?: Record<string, number | string>[];
};

/** A render artifact the backend attaches to an assistant message (download/chart). */
type MessageArtifact = {
  kind: string;
  download_path?: string;
  filename?: string;
  row_count?: number;
  format?: string;
  chart?: ChartSpec;
};

function readArtifacts(message: ChatMessage): MessageArtifact[] {
  const raw = (message.tool_result as { artifacts?: unknown } | null)?.artifacts;
  return Array.isArray(raw) ? (raw as MessageArtifact[]) : [];
}

export function MessageBubble({
  message,
  expanded,
  confirming,
  onConfirm,
  t,
}: {
  message: ChatMessage;
  expanded: boolean;
  confirming: boolean;
  onConfirm: () => void;
  t: (k: string) => string;
}) {
  const isUser = message.role === "user";
  const isToolCall = message.role === "tool_call";

  if (isToolCall) {
    return (
      <div className="flex items-start gap-2">
        <span className="mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-full icon-chip-warning shadow-sm">
          <Lightning aria-hidden weight="fill" className="size-3 text-white" />
        </span>
        <div className="rounded-xl border border-[var(--amber-100)] bg-[var(--amber-50)]/90 px-3 py-2 text-xs text-[var(--amber-700)]">
          <p>{message.content}</p>
          {message.requires_confirmation && (
            <button
              type="button"
              onClick={onConfirm}
              disabled={confirming}
              className="mt-2 inline-flex items-center gap-1.5 rounded-lg bg-[var(--amber-600)] px-2.5 py-1.5 text-xs font-semibold text-white outline-none transition hover:bg-[var(--amber-700)] focus-visible:ring-2 focus-visible:ring-[var(--amber-400)] disabled:cursor-not-allowed disabled:opacity-60"
            >
              {confirming && (
                <Spinner aria-hidden weight="bold" className="size-3 animate-spin" />
              )}
              {confirming ? t("confirmingAction") : t("confirmAction")}
            </button>
          )}
        </div>
      </div>
    );
  }

  return (
    <div
      className={cn(
        "flex items-end gap-2",
        isUser ? "flex-row-reverse" : "flex-row",
      )}
    >
      {!isUser && (
        <span className="mb-0.5 flex size-6 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-[var(--brand-primary)] to-[var(--brand-teal)] shadow-sm">
          <Sparkle aria-hidden weight="fill" className="size-3.5 text-white" />
        </span>
      )}
      <div
        className={cn(
          "rounded-2xl px-3 py-2.5 text-sm leading-relaxed",
          expanded ? "max-w-[min(72ch,82%)]" : "max-w-[82%]",
          isUser
            ? "rounded-br-sm bg-[var(--text-primary)] text-[var(--text-inverted)] shadow-[0_1px_6px_rgba(0,0,0,0.16)]"
            : "rounded-bl-sm border border-[var(--glass-border-strong)] bg-[var(--glass-surface-heavy)] text-[var(--text-primary)] shadow-[0_1px_4px_rgba(11,34,57,0.06)]",
        )}
      >
        {isUser ? (
          <UserBubbleContent content={message.content} />
        ) : (
          <FormattedContent content={message.content} isUser={false} />
        )}
        {!isUser && <MessageArtifacts message={message} />}
      </div>
    </div>
  );
}

/** User message: strip machine-readable attachment refs, show paperclip chips. */
function UserBubbleContent({ content }: { content: string }) {
  const { text, filenames } = extractAttachmentRefs(content);
  return (
    <div className="flex flex-col gap-1.5">
      {text && <FormattedContent content={text} isUser />}
      {filenames.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {filenames.map((name, i) => (
            <span
              key={i}
              className="inline-flex max-w-[200px] items-center gap-1 rounded-lg bg-white/15 px-2 py-1 text-[11px]"
            >
              <Paperclip aria-hidden weight="bold" className="size-3 shrink-0" />
              <span className="truncate">{name}</span>
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

/** Render backend-attached artifacts (currently: download buttons). */
function MessageArtifacts({ message }: { message: ChatMessage }) {
  const artifacts = readArtifacts(message);
  if (artifacts.length === 0) return null;
  return (
    <div className="mt-2 flex flex-col gap-1.5">
      {artifacts.map((a, i) =>
        a.kind === "download" && a.download_path ? (
          <DownloadArtifact key={i} artifact={a} />
        ) : a.kind === "chart" && a.chart ? (
          <ChartArtifact key={i} artifact={a} />
        ) : null,
      )}
    </div>
  );
}

function DownloadArtifact({ artifact }: { artifact: MessageArtifact }) {
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);
  const onDownload = async () => {
    if (!artifact.download_path) return;
    setBusy(true);
    setFailed(false);
    try {
      const base = env.apiBaseUrl.replace(/\/$/, "");
      const token = getAccessToken();
      const res = await fetch(`${base}${artifact.download_path}`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
        credentials: "include",
      });
      if (!res.ok) throw new Error(`download failed: ${res.status}`);
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = artifact.filename || "export.xlsx";
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch {
      setFailed(true);
    } finally {
      setBusy(false);
    }
  };
  return (
    <button
      type="button"
      onClick={onDownload}
      disabled={busy}
      className="inline-flex w-fit items-center gap-2 rounded-xl border border-[var(--brand-primary)]/25 bg-[var(--brand-primary)]/5 px-3 py-2 text-xs font-semibold text-[var(--brand-primary)] outline-none transition hover:bg-[var(--brand-primary)]/10 hover:border-[var(--brand-primary)]/40 focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/30 disabled:cursor-not-allowed disabled:opacity-60"
    >
      {busy ? (
        <Spinner aria-hidden weight="bold" className="size-4 animate-spin" />
      ) : (
        <DownloadSimple aria-hidden weight="bold" className="size-4 shrink-0" />
      )}
      <span className="flex flex-col items-start leading-tight">
        <span>{failed ? "Tải thất bại — thử lại" : (artifact.filename ?? "Tải tệp")}</span>
        {typeof artifact.row_count === "number" && !failed && (
          <span className="text-[10px] font-normal text-[var(--text-muted)]">
            {artifact.format === "xlsx" ? "Excel" : "Tệp"} · {artifact.row_count} dòng
          </span>
        )}
      </span>
    </button>
  );
}

const CHART_COLORS = [
  "var(--brand-primary)",
  "var(--brand-teal)",
  "var(--amber-600)",
];

/** Render a backend-emitted analytics chart (bar/line) with Recharts. */
function ChartArtifact({ artifact }: { artifact: MessageArtifact }) {
  const chart = artifact.chart;
  if (!chart || !Array.isArray(chart.data) || chart.data.length === 0) return null;
  const xKey = chart.x_key ?? "label";
  const series = chart.series && chart.series.length > 0 ? chart.series : [{ key: "value" }];
  const isLine = chart.type === "line";
  const many = chart.data.length > 4;
  return (
    <figure className="mt-1 w-full rounded-xl border border-[var(--glass-border-strong)] bg-[var(--surface-card)]/60 p-3">
      {chart.title && (
        <figcaption className="mb-2 text-xs font-semibold text-[var(--text-secondary)]">
          {chart.title}
        </figcaption>
      )}
      <div className="h-[220px] w-full">
        <ResponsiveContainer width="100%" height="100%">
          {isLine ? (
            <LineChart data={chart.data} margin={{ top: 4, right: 8, bottom: 4, left: -14 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--glass-border-strong)" vertical={false} />
              <XAxis
                dataKey={xKey}
                tick={{ fontSize: 10, fill: "var(--text-muted)" }}
                interval="preserveStartEnd"
              />
              <YAxis
                tick={{ fontSize: 10, fill: "var(--text-muted)" }}
                allowDecimals={false}
                width={30}
              />
              <Tooltip contentStyle={{ fontSize: 12, borderRadius: 8 }} />
              {series.length > 1 && <Legend wrapperStyle={{ fontSize: 11 }} />}
              {series.map((sr, i) => (
                <Line
                  key={sr.key}
                  type="monotone"
                  dataKey={sr.key}
                  name={sr.name ?? sr.key}
                  stroke={CHART_COLORS[i % CHART_COLORS.length]}
                  strokeWidth={2}
                  dot={{ r: 3 }}
                />
              ))}
            </LineChart>
          ) : (
            <BarChart data={chart.data} margin={{ top: 4, right: 8, bottom: 4, left: -14 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--glass-border-strong)" vertical={false} />
              <XAxis
                dataKey={xKey}
                tick={{ fontSize: 10, fill: "var(--text-muted)" }}
                interval={0}
                angle={many ? -20 : 0}
                textAnchor={many ? "end" : "middle"}
                height={many ? 52 : 24}
              />
              <YAxis
                tick={{ fontSize: 10, fill: "var(--text-muted)" }}
                allowDecimals={false}
                width={30}
              />
              <Tooltip contentStyle={{ fontSize: 12, borderRadius: 8 }} cursor={{ fill: "rgba(0,0,0,0.04)" }} />
              {series.length > 1 && <Legend wrapperStyle={{ fontSize: 11 }} />}
              {series.map((sr, i) => (
                <Bar
                  key={sr.key}
                  dataKey={sr.key}
                  name={sr.name ?? sr.key}
                  fill={CHART_COLORS[i % CHART_COLORS.length]}
                  radius={[3, 3, 0, 0]}
                  maxBarSize={44}
                />
              ))}
            </BarChart>
          )}
        </ResponsiveContainer>
      </div>
    </figure>
  );
}

export function StreamingBubble({
  text,
  expanded,
}: {
  text: string;
  expanded: boolean;
}) {
  return (
    <div className="flex items-end gap-2">
      <span className="mb-0.5 flex size-6 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-[var(--brand-primary)] to-[var(--brand-teal)] shadow-sm">
        <Sparkle aria-hidden weight="fill" className="size-3.5 text-white" />
      </span>
      <div
        className={cn(
          "rounded-2xl rounded-bl-sm border border-[var(--glass-border-strong)] bg-[var(--glass-surface-heavy)] px-3 py-2.5 text-sm leading-relaxed text-[var(--text-primary)] shadow-[0_1px_4px_rgba(11,34,57,0.06)]",
          expanded ? "max-w-[min(72ch,82%)]" : "max-w-[82%]",
        )}
      >
        <FormattedContent content={text} isUser={false} />
        {/* Blinking cursor */}
        <span className="ml-0.5 inline-block h-3.5 w-0.5 animate-pulse rounded-full bg-[var(--brand-primary)]" />
      </div>
    </div>
  );
}

export function AssistantActivity({
  status,
  toolName,
}: {
  status: string | null;
  toolName: string | null;
}) {
  const label = toolName ? (TOOL_LABELS[toolName] ?? "Đang xử lý…") : "Đang xử lý…";
  return (
    <div className="flex items-center gap-2 self-start" aria-live="polite">
      <span className="flex size-6 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-[var(--ai-accent)] to-[var(--teal-600)] shadow-sm">
        <MagnifyingGlass aria-hidden weight="fill" className="size-3 text-white" />
      </span>
      <div className="rounded-2xl rounded-bl-sm border border-[var(--ai-accent)]/25 bg-[var(--ai-accent-soft)] px-3 py-2 text-xs font-medium text-[var(--teal-700)]">
        <div className="flex items-center gap-2">
          <Spinner aria-hidden weight="bold" className="size-3 animate-spin" />
          {toolName ? label : (status ?? "Đang suy nghĩ…")}
        </div>
        {status && toolName && (
          <p className="mt-0.5 text-[11px] font-normal text-[var(--teal-700)]/72">{status}</p>
        )}
      </div>
    </div>
  );
}

const _TABLE_ROW = /^\s*\|.*\|\s*$/;
const _TABLE_SEP = /^\s*\|?[\s:|-]*-[\s:|-]*\|?\s*$/;

function parseCells(row: string): string[] {
  return row
    .trim()
    .replace(/^\|/, "")
    .replace(/\|$/, "")
    .split("|")
    .map((c) => c.trim());
}

/** Render plain text with basic markdown: **bold**, lists, tables, internal links. */
export function FormattedContent({
  content,
  isUser,
}: {
  content: string;
  isUser: boolean;
}) {
  const lines = content.split("\n").filter((l) => l.trim() !== "");
  const nodes: React.ReactNode[] = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i]!;
    // Markdown table: a `| ... |` row immediately followed by a `|---|` separator.
    if (_TABLE_ROW.test(line) && i + 1 < lines.length && _TABLE_SEP.test(lines[i + 1]!)) {
      const body: string[] = [];
      let j = i + 2;
      while (j < lines.length && _TABLE_ROW.test(lines[j]!) && !_TABLE_SEP.test(lines[j]!)) {
        body.push(lines[j]!);
        j += 1;
      }
      nodes.push(<MarkdownTable key={i} header={line} rows={body} isUser={isUser} />);
      i = j;
      continue;
    }
    nodes.push(renderLine(line, i, isUser));
    i += 1;
  }
  return <div className="space-y-1">{nodes}</div>;
}

function renderLine(line: string, key: number, isUser: boolean): React.ReactNode {
  if (line.startsWith("- ") || line.startsWith("• ") || line.startsWith("* ")) {
    return (
      <p key={key} className="pl-3">
        <span className="mr-1.5 opacity-50">•</span>
        {renderInline(line.replace(/^[-•*]\s*/, ""), isUser)}
      </p>
    );
  }
  const numberedMatch = line.match(/^(\d+)\.\s+(.+)/);
  if (numberedMatch) {
    return (
      <p key={key} className="pl-3">
        <span className="mr-1.5 opacity-60 font-medium">{numberedMatch[1]}.</span>
        {renderInline(numberedMatch[2] ?? "", isUser)}
      </p>
    );
  }
  if (line.match(/^\/\w/)) {
    return (
      <a
        key={key}
        href={line}
        className={cn(
          "flex items-center gap-1 text-xs font-medium underline underline-offset-2",
          isUser ? "text-white/90" : "text-[var(--brand-primary)]",
        )}
      >
        {line}
        <ArrowSquareOut aria-hidden weight="bold" className="size-3 shrink-0" />
      </a>
    );
  }
  return <p key={key}>{renderInline(line, isUser)}</p>;
}

function MarkdownTable({
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
  return (
    <div className="my-1.5 overflow-x-auto rounded-lg border border-[var(--glass-border)]">
      <table className="w-full border-collapse text-[11px]">
        <thead>
          <tr className="bg-[var(--brand-primary)]/8">
            {headers.map((h, i) => (
              <th
                key={i}
                className="border-b border-[var(--glass-border)] px-2 py-1.5 text-left font-semibold text-[var(--text-primary)] whitespace-nowrap"
              >
                {renderInline(h, isUser)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {body.map((r, ri) => (
            <tr key={ri} className="even:bg-[var(--bg-subtle)]/40">
              {r.map((c, ci) => (
                <td
                  key={ci}
                  className="border-b border-[var(--glass-border)]/60 px-2 py-1 align-top text-[var(--text-secondary)]"
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

/** Bold (**text**) inline rendering. */
function renderInline(text: string, isUser: boolean): React.ReactNode {
  const parts = text.split(/(\*\*[^*]+\*\*)/g);
  if (parts.length === 1) return text;
  return parts.map((part, i) => {
    if (part.startsWith("**") && part.endsWith("**")) {
      return (
        <strong key={i} className={isUser ? "font-bold text-white" : "font-semibold"}>
          {part.slice(2, -2)}
        </strong>
      );
    }
    return part;
  });
}

export function TypingIndicator() {
  return (
    <div className="flex items-end gap-2">
      <span className="mb-0.5 flex size-6 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-[var(--brand-primary)] to-[var(--brand-teal)] shadow-sm">
        <Sparkle aria-hidden weight="fill" className="size-3.5 text-white" />
      </span>
      <div className="flex items-center gap-1.5 rounded-2xl rounded-bl-sm border border-[var(--glass-border-strong)] bg-[var(--glass-surface-heavy)] px-4 py-3 shadow-[0_1px_4px_rgba(11,34,57,0.06)]">
        {[0, 1, 2].map((i) => (
          <span
            key={i}
            className="size-1.5 rounded-full bg-[var(--text-muted)] animate-bounce"
            style={{ animationDelay: `${i * 0.15}s` }}
          />
        ))}
      </div>
    </div>
  );
}
