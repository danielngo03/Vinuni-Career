"use client";

import { useState } from "react";
import {
  ArrowSquareOut,
  DownloadSimple,
  Lightning,
  MagnifyingGlass,
  Robot,
  Spinner,
} from "@phosphor-icons/react";
import { cn } from "@/lib/utils";
import { env } from "@/lib/env";
import type { ChatMessage } from "@/lib/api";
import { getAccessToken } from "@/lib/api/session";
import { TOOL_LABELS } from "./constants";

/** A render artifact the backend attaches to an assistant message (download/chart). */
type MessageArtifact = {
  kind: string;
  download_path?: string;
  filename?: string;
  row_count?: number;
  format?: string;
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
          <Robot aria-hidden weight="fill" className="size-3.5 text-white" />
        </span>
      )}
      <div
        className={cn(
          "rounded-2xl px-3 py-2.5 text-sm leading-relaxed",
          expanded ? "max-w-[min(72ch,82%)]" : "max-w-[82%]",
          isUser
            ? "rounded-br-sm icon-chip-primary text-white shadow-[var(--shadow-sm)]"
            : "rounded-bl-sm border border-[var(--glass-border-strong)] bg-[var(--glass-surface-heavy)] text-[var(--text-primary)] shadow-[0_1px_4px_rgba(11,34,57,0.06)]",
        )}
      >
        <FormattedContent content={message.content} isUser={isUser} />
        {!isUser && <MessageArtifacts message={message} />}
      </div>
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
        <Robot aria-hidden weight="fill" className="size-3.5 text-white" />
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
        <Robot aria-hidden weight="fill" className="size-3.5 text-white" />
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
