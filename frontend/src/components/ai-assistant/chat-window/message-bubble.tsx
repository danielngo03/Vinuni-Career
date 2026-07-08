"use client";

import { useEffect, useRef, useState } from "react";
import {
  ArrowsClockwise,
  ArrowSquareOut,
  Lightning,
  MagnifyingGlass,
  Paperclip,
  PencilSimple,
  Robot,
  Spinner,
} from "@phosphor-icons/react";
import { cn } from "@/lib/utils";
import type { ChatMessage } from "@/lib/api";
import { extractAttachmentRefs, MAX_INPUT_LENGTH, TOOL_LABELS } from "./constants";
import {
  analyzeColumns,
  segmentContent,
  shouldRenderBars,
  type ColumnAlign,
  type ColumnStat,
  type ParsedTable,
} from "./markdown-table";

export function MessageBubble({
  message,
  expanded,
  confirming,
  onConfirm,
  /** True while any turn (send / regenerate / edit / tool confirm) is in flight;
   * gates the edit + regenerate affordances so only one action runs at a time. */
  busy = false,
  /** Marks the newest assistant reply so only it exposes the regenerate control. */
  isLastAssistant = false,
  /** The regenerate request for this (last) assistant reply is in flight. */
  regenerating = false,
  onRegenerate,
  /** This user message is currently in the inline edit-and-rerun editor. */
  editing = false,
  /** The edit request for this user message is in flight. */
  savingEdit = false,
  onStartEdit,
  onCancelEdit,
  onSubmitEdit,
  t,
}: {
  message: ChatMessage;
  expanded: boolean;
  confirming: boolean;
  onConfirm: () => void;
  busy?: boolean;
  isLastAssistant?: boolean;
  regenerating?: boolean;
  onRegenerate?: () => void;
  editing?: boolean;
  savingEdit?: boolean;
  onStartEdit?: () => void;
  onCancelEdit?: () => void;
  onSubmitEdit?: (text: string) => void;
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

  // User bubbles may carry appended analyze-attachment reference lines. Strip
  // them from the visible text and render a clean paperclip chip per file
  // instead, so the raw machine-readable ref/id never shows.
  const parsed = isUser ? extractAttachmentRefs(message.content) : null;
  const displayText = parsed ? parsed.text : message.content;
  const attachmentNames = parsed?.filenames ?? [];

  // Only persisted user messages can be edited-and-rerun. Optimistic drafts
  // (opt-*) have no server id yet, so the edit affordance stays hidden for them.
  const canEdit =
    isUser && !!onSubmitEdit && !message.id.startsWith("opt-");

  // Swap the bubble for the inline edit-and-rerun editor when armed.
  if (canEdit && editing) {
    return (
      <UserEditEditor
        initialText={displayText}
        saving={savingEdit}
        expanded={expanded}
        onCancel={() => onCancelEdit?.()}
        onSubmit={(text) => onSubmitEdit?.(text)}
        t={t}
      />
    );
  }

  return (
    <div
      className={cn(
        "group flex items-end gap-2",
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
        {displayText && <FormattedContent content={displayText} isUser={isUser} />}
        {attachmentNames.length > 0 && (
          <ul
            aria-label={t("attachmentsLabel")}
            className={cn("flex flex-wrap gap-1.5", displayText && "mt-1.5")}
          >
            {attachmentNames.map((name, i) => (
              <li
                key={i}
                className="flex max-w-full items-center gap-1 rounded-lg bg-white/15 px-2 py-1 text-xs"
              >
                <Paperclip aria-hidden weight="bold" className="size-3 shrink-0" />
                <span className="truncate" title={name}>
                  {name}
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>

      {/* Edit-and-rerun affordance: reveals on hover/focus so many user
          bubbles stay quiet, but the button remains keyboard-reachable. */}
      {canEdit && (
        <button
          type="button"
          onClick={() => onStartEdit?.()}
          disabled={busy}
          aria-label={t("editMessage")}
          title={t("editMessage")}
          className={cn(
            "mb-0.5 shrink-0 self-end rounded-lg p-1 opacity-0 outline-none transition",
            "text-[var(--text-muted)] hover:bg-[var(--bg-subtle)] hover:text-[var(--text-primary)]",
            "group-hover:opacity-100 focus-visible:opacity-100 focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/40",
            "disabled:cursor-not-allowed disabled:hover:bg-transparent",
          )}
        >
          <PencilSimple aria-hidden weight="bold" className="size-3.5" />
        </button>
      )}

      {/* Regenerate the newest assistant reply. */}
      {isLastAssistant && onRegenerate && (
        <button
          type="button"
          onClick={onRegenerate}
          disabled={busy}
          aria-label={t("regenerate")}
          title={t("regenerate")}
          className={cn(
            "mb-0.5 shrink-0 self-end rounded-lg p-1 outline-none transition",
            "text-[var(--text-muted)] hover:bg-[var(--bg-subtle)] hover:text-[var(--text-primary)]",
            "focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/40",
            "disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:bg-transparent",
          )}
        >
          {regenerating ? (
            <Spinner aria-hidden weight="bold" className="size-3.5 animate-spin" />
          ) : (
            <ArrowsClockwise aria-hidden weight="bold" className="size-3.5" />
          )}
        </button>
      )}
    </div>
  );
}

/**
 * Inline edit-and-rerun editor for a user message. Focuses the textarea (caret
 * at end) on mount; Esc cancels, Cmd/Ctrl+Enter saves, and the Save button is
 * blocked while the text is empty or a save is in flight. Editing truncates and
 * replays the conversation server-side, so the helper line warns the user.
 */
function UserEditEditor({
  initialText,
  saving,
  expanded,
  onCancel,
  onSubmit,
  t,
}: {
  initialText: string;
  saving: boolean;
  expanded: boolean;
  onCancel: () => void;
  onSubmit: (text: string) => void;
  t: (k: string) => string;
}) {
  const [draft, setDraft] = useState(initialText);
  const ref = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (el) {
      el.focus();
      el.setSelectionRange(el.value.length, el.value.length);
    }
  }, []);

  const valid = draft.trim().length > 0;

  function submit() {
    if (!valid || saving) return;
    onSubmit(draft.trim());
  }

  return (
    <div className="flex flex-col items-end gap-1">
      <div
        className={cn(
          "w-full rounded-2xl rounded-br-sm border border-[var(--brand-primary)]/45 bg-[var(--glass-surface-heavy)] p-2",
          expanded ? "max-w-[min(72ch,92%)]" : "max-w-[92%]",
        )}
      >
        <textarea
          ref={ref}
          value={draft}
          onChange={(e) => setDraft(e.target.value.slice(0, MAX_INPUT_LENGTH))}
          onKeyDown={(e) => {
            if (e.key === "Escape") {
              e.preventDefault();
              onCancel();
            } else if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
              e.preventDefault();
              submit();
            }
          }}
          rows={2}
          disabled={saving}
          aria-label={t("editMessage")}
          className="w-full resize-none rounded-lg bg-transparent px-1 py-0.5 text-sm leading-relaxed text-[var(--text-primary)] outline-none disabled:opacity-60"
          style={{ maxHeight: "160px" }}
        />
        <div className="mt-1.5 flex items-end justify-between gap-2">
          <p className="min-w-0 flex-1 text-[11px] leading-tight text-[var(--text-muted)]">
            {t("editRerunHint")}
          </p>
          <div className="flex shrink-0 items-center gap-1.5">
            <button
              type="button"
              onClick={onCancel}
              disabled={saving}
              className="rounded-md px-2 py-1 text-xs font-semibold text-[var(--text-secondary)] outline-none transition-colors hover:bg-[var(--bg-subtle)] focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/40 disabled:opacity-60"
            >
              {t("cancel")}
            </button>
            <button
              type="button"
              onClick={submit}
              disabled={!valid || saving}
              className="inline-flex items-center gap-1.5 rounded-md bg-[var(--brand-primary)] px-2.5 py-1 text-xs font-semibold text-white outline-none transition-colors hover:bg-[var(--brand-primary)]/90 focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/40 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {saving && (
                <Spinner aria-hidden weight="bold" className="size-3 animate-spin" />
              )}
              {t("editSave")}
            </button>
          </div>
        </div>
      </div>
    </div>
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

/**
 * Render assistant/user text with markdown-lite support: **bold**, bullet and
 * numbered lists, internal links, and GitHub-Flavored pipe tables (with inline
 * monochrome bars for fully-numeric columns).
 *
 * Tables are only parsed for assistant messages — user bubbles use the ink
 * surface and keep the original plain-line rendering. Table parsing degrades
 * gracefully: anything that is not a well-formed pipe table falls back to the
 * existing line renderer, so a malformed/partial table never crashes the bubble.
 */
export function FormattedContent({
  content,
  isUser,
}: {
  content: string;
  isUser: boolean;
}) {
  // User bubbles keep the legacy plain-line rendering (no tables on the ink
  // surface). Assistant/streaming bubbles get table segmentation.
  if (isUser) {
    return <LinesBlock lines={content.split("\n")} isUser={isUser} />;
  }

  const blocks = segmentContent(content);
  return (
    <div className="space-y-1.5">
      {blocks.map((block, bi) =>
        block.type === "table" ? (
          <MarkdownTable key={bi} table={block.table} />
        ) : (
          <LinesBlock key={bi} lines={block.lines} isUser={isUser} />
        ),
      )}
    </div>
  );
}

/** Column alignment: explicit separator alignment wins, else numeric → right. */
function resolveAlign(explicit: ColumnAlign, stat: ColumnStat | undefined): ColumnAlign {
  if (explicit) return explicit;
  if (stat?.numeric) return "right";
  return "left";
}

function alignClass(align: ColumnAlign): string {
  if (align === "right") return "text-right";
  if (align === "center") return "text-center";
  return "text-left";
}

/**
 * Render a parsed pipe table as a clean v9 Monochrome `<table>`. Fully-numeric
 * columns get a subtle inline bar (ink fill on a muted track) scaled to the
 * column max, giving a lightweight "column chart" feel without a chart library.
 * The wrapper scrolls horizontally so wide tables never overflow the bubble.
 */
function MarkdownTable({ table }: { table: ParsedTable }) {
  const stats = analyzeColumns(table);

  return (
    <div className="my-1 overflow-x-auto rounded-lg border border-[var(--border-default)]">
      <table className="w-full border-collapse text-xs text-[var(--text-primary)]">
        <thead>
          <tr>
            {table.headers.map((header, c) => (
              <th
                key={c}
                scope="col"
                className={cn(
                  "whitespace-nowrap border-b border-[var(--border-default)] bg-[var(--bg-subtle)] px-2.5 py-1.5 text-[10px] font-semibold uppercase tracking-wide text-[var(--text-muted)]",
                  alignClass(resolveAlign(table.aligns[c] ?? null, stats[c])),
                )}
              >
                {header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {table.rows.map((row, r) => (
            <tr
              key={r}
              className={r % 2 === 1 ? "bg-[var(--bg-subtle)]/50" : undefined}
            >
              {table.headers.map((_, c) => {
                const stat = stats[c];
                const align = resolveAlign(table.aligns[c] ?? null, stat);
                const cell = row[c] ?? "";
                const value = stat?.values[r] ?? null;
                const withBar =
                  stat !== undefined &&
                  shouldRenderBars(stat) &&
                  value !== null;
                const pct =
                  withBar && stat && value !== null && value > 0
                    ? Math.max(3, (value / stat.max) * 100)
                    : 0;
                return (
                  <td
                    key={c}
                    className={cn(
                      "border-t border-[var(--border-subtle)] px-2.5 py-1.5 align-middle",
                      alignClass(align),
                      align === "right" ? "tabular-nums" : undefined,
                    )}
                  >
                    <span>{cell}</span>
                    {withBar && (
                      <span
                        role="img"
                        aria-label={cell}
                        className="mt-1 block h-1 w-full overflow-hidden rounded-full bg-[var(--bg-muted)]"
                      >
                        <span
                          className="block h-full rounded-full bg-[var(--text-primary)]/70"
                          style={{ width: `${pct}%` }}
                        />
                      </span>
                    )}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** Render a run of non-table lines with **bold**, lists, and internal links. */
function LinesBlock({ lines: rawLines, isUser }: { lines: string[]; isUser: boolean }) {
  const lines = rawLines.filter((l) => l.trim() !== "");
  if (lines.length === 0) return null;

  return (
    <div className="space-y-1">
      {lines.map((line, i) => {
        if (line.startsWith("- ") || line.startsWith("• ") || line.startsWith("* ")) {
          return (
            <p key={i} className="pl-3">
              <span className="mr-1.5 opacity-50">•</span>
              {renderInline(line.replace(/^[-•*]\s*/, ""), isUser)}
            </p>
          );
        }
        // Numbered lists
        const numberedMatch = line.match(/^(\d+)\.\s+(.+)/);
        if (numberedMatch) {
          return (
            <p key={i} className="pl-3">
              <span className="mr-1.5 opacity-60 font-medium">{numberedMatch[1]}.</span>
              {renderInline(numberedMatch[2] ?? "", isUser)}
            </p>
          );
        }
        // Internal path → link
        if (line.match(/^\/\w/)) {
          return (
            <a
              key={i}
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
        return <p key={i}>{renderInline(line, isUser)}</p>;
      })}
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
