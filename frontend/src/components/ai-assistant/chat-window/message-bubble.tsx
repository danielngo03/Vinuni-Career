"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import {
  Loader2,
  Paperclip,
  Pencil,
  Sparkles,
  Zap,
} from "lucide-react";
import { cn } from "@/lib/utils";
import type { ChatMessage } from "@/lib/api";
import { StatusChip } from "@/components/kit";
import { extractAttachmentRefs, MAX_INPUT_LENGTH } from "./constants";
import { contentHasTable, FormattedContent } from "./markdown";
import { MessageArtifacts, readArtifacts } from "./artifacts";

/** How a pending tool-call was resolved (server confirm or local cancel). */
export type ToolResolution = "confirmed" | "canceled";

/**
 * Assistant identity marker — one restrained `--content-ai` accent (v10 §1.1.2).
 * Solid soft-tint tile, no gradient blob, no glass.
 */
function AssistantAvatar() {
  return (
    <span
      aria-hidden
      className="mb-0.5 flex size-6 shrink-0 items-center justify-center rounded-lg bg-[var(--content-ai-soft)]"
    >
      <Sparkles strokeWidth={1.9} className="size-3.5 text-[var(--content-ai)]" />
    </span>
  );
}

export function MessageBubble({
  message,
  expanded,
  confirmBusy = null,
  resolution = null,
  onConfirm,
  onCancel,
  editable = false,
  editing = false,
  editBusy = false,
  onEditStart,
  onEditCancel,
  onEditSubmit,
}: {
  message: ChatMessage;
  expanded: boolean;
  /** Which decision is currently in flight for this tool-call message. */
  confirmBusy?: "confirm" | "cancel" | null;
  /** Locally-known resolution (falls back to `confirmed_at` from the server). */
  resolution?: ToolResolution | null;
  onConfirm?: () => void;
  onCancel?: () => void;
  editable?: boolean;
  editing?: boolean;
  editBusy?: boolean;
  onEditStart?: () => void;
  onEditCancel?: () => void;
  onEditSubmit?: (text: string) => void;
}) {
  const t = useTranslations("aiAssistant");
  const isUser = message.role === "user";

  // Proposed write action — a distinct confirmable card. The confirmation gate
  // is preserved exactly: AI never auto-executes; the user must decide.
  if (message.role === "tool_call") {
    return (
      <ToolCallCard
        message={message}
        busy={confirmBusy}
        resolution={resolution}
        onConfirm={onConfirm}
        onCancel={onCancel}
      />
    );
  }

  // Inline edit mode for the last user message (PATCH → server truncates + re-runs).
  if (isUser && editing) {
    return (
      <UserEditBubble
        initial={extractAttachmentRefs(message.content).text}
        busy={editBusy}
        onSubmit={onEditSubmit}
        onCancel={onEditCancel}
        t={t}
      />
    );
  }

  const artifacts = isUser ? [] : readArtifacts(message);
  // Artifact-bearing or table-bearing bubbles take the full available width so
  // charts/tables/cards can breathe; plain text keeps a readable cap.
  const wide = !isUser && (artifacts.length > 0 || contentHasTable(message.content));

  return (
    <div className="group flex flex-col">
      <div
        className={cn(
          "flex gap-2",
          isUser ? "flex-row-reverse items-end" : wide ? "items-start" : "items-end",
        )}
      >
        {!isUser && <AssistantAvatar />}
        <div
          className={cn(
            "type-body min-w-0 rounded-2xl px-3 py-2.5 [overflow-wrap:anywhere] [word-break:break-word]",
            wide
              ? "w-full max-w-full flex-1"
              : expanded
                ? "max-w-[min(72ch,82%)]"
                : "max-w-[82%]",
            isUser
              ? "rounded-br-sm bg-[var(--brand-primary)] text-[var(--text-inverted)]"
              : "rounded-bl-sm border border-[var(--border-default)] bg-[var(--bg-subtle)] text-[var(--text-primary)] shadow-[var(--shadow-sm)]",
          )}
        >
          {isUser ? (
            <UserBubbleContent content={message.content} />
          ) : (
            <FormattedContent
              content={message.content}
              isUser={false}
              constrainText={expanded && wide}
            />
          )}
          {!isUser && <MessageArtifacts message={message} expanded={expanded} />}
        </div>
        {isUser && editable && (
          <button
            type="button"
            onClick={onEditStart}
            aria-label={t("editMessage")}
            title={t("editMessage")}
            className="shrink-0 self-end rounded-lg p-1.5 text-[var(--text-muted)] opacity-60 outline-none transition-opacity hover:bg-[var(--bg-muted)] hover:text-[var(--text-primary)] focus-visible:opacity-100 focus-visible:ring-2 focus-visible:ring-[var(--field-focus-border)] sm:opacity-0 sm:group-focus-within:opacity-100 sm:group-hover:opacity-100"
          >
            <Pencil aria-hidden strokeWidth={1.9} className="size-3.5" />
          </button>
        )}
      </div>
    </div>
  );
}

/** Inline textarea replacing the last user bubble while editing. */
function UserEditBubble({
  initial,
  busy,
  onSubmit,
  onCancel,
  t,
}: {
  initial: string;
  busy: boolean;
  onSubmit?: (text: string) => void;
  onCancel?: () => void;
  t: (k: string) => string;
}) {
  const [draft, setDraft] = useState(initial);
  const canSave = draft.trim().length > 0 && !busy;
  return (
    <div className="flex justify-end">
      <div className="w-full max-w-[min(60ch,92%)] rounded-2xl border border-[var(--field-focus-border)] bg-[var(--surface-card)] p-2 shadow-[var(--shadow-sm)]">
        <textarea
          value={draft}
          onChange={(e) => setDraft(e.target.value.slice(0, MAX_INPUT_LENGTH))}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              if (canSave) onSubmit?.(draft.trim());
            }
            if (e.key === "Escape") onCancel?.();
          }}
          autoFocus
          rows={3}
          disabled={busy}
          aria-label={t("editMessage")}
          className="type-small w-full resize-none rounded-lg bg-transparent px-1.5 py-1 leading-5 text-[var(--text-primary)] outline-none [overflow-wrap:anywhere] [word-break:break-word] disabled:opacity-60"
        />
        <div className="mt-1 flex items-center justify-end gap-1.5">
          <button
            type="button"
            onClick={onCancel}
            disabled={busy}
            className="type-caption rounded-full px-3 py-1.5 font-medium text-[var(--text-secondary)] outline-none transition-colors hover:bg-[var(--bg-muted)] hover:text-[var(--text-primary)] focus-visible:ring-2 focus-visible:ring-[var(--field-focus-border)] disabled:cursor-not-allowed disabled:opacity-50"
          >
            {t("editCancel")}
          </button>
          <button
            type="button"
            onClick={() => canSave && onSubmit?.(draft.trim())}
            disabled={!canSave}
            className="type-caption inline-flex items-center gap-1.5 rounded-full bg-[var(--btn-primary-bg)] px-3 py-1.5 font-semibold text-[var(--btn-primary-fg)] shadow-[var(--shadow-sm)] outline-none transition-colors hover:opacity-90 focus-visible:ring-2 focus-visible:ring-[var(--field-focus-border)] disabled:cursor-not-allowed disabled:opacity-50"
          >
            {busy && <Loader2 aria-hidden className="size-3 animate-spin" />}
            {t("editSend")}
          </button>
        </div>
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
              className="type-caption inline-flex max-w-[200px] items-center gap-1 rounded-md bg-[var(--text-inverted)]/15 px-2 py-1 font-normal"
            >
              <Paperclip aria-hidden strokeWidth={1.9} className="size-3 shrink-0" />
              <span className="truncate">{name}</span>
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

/* ------------------------------- Tool confirm ------------------------------ */

function prettifyKey(key: string): string {
  const s = key.replace(/_/g, " ").trim();
  return s.charAt(0).toUpperCase() + s.slice(1);
}

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

function formatArgValue(v: unknown): string {
  if (v === null || v === undefined) return "—";
  if (typeof v === "string") {
    const s = UUID_RE.test(v) ? `${v.slice(0, 8)}…` : v;
    return s.length > 160 ? `${s.slice(0, 160)}…` : s;
  }
  if (typeof v === "number" || typeof v === "boolean") return String(v);
  if (Array.isArray(v)) return v.map((x) => formatArgValue(x)).join(", ");
  try {
    const s = JSON.stringify(v);
    return s.length > 160 ? `${s.slice(0, 160)}…` : s;
  } catch {
    return "—";
  }
}

/** Pending/resolved AI write-action card: labeled arg summary + confirm/cancel. */
function ToolCallCard({
  message,
  busy,
  resolution,
  onConfirm,
  onCancel,
}: {
  message: ChatMessage;
  busy: "confirm" | "cancel" | null;
  resolution: ToolResolution | null;
  onConfirm?: () => void;
  onCancel?: () => void;
}) {
  const t = useTranslations("aiAssistant");
  const toolName = message.tool_name;
  const title =
    toolName && t.has(`toolNames.${toolName}`)
      ? t(`toolNames.${toolName}`)
      : t("confirmTitle");
  const args =
    message.tool_args && typeof message.tool_args === "object"
      ? Object.entries(message.tool_args).filter(([, v]) => v !== null && v !== undefined)
      : [];
  const resolved: ToolResolution | null =
    resolution ?? (message.confirmed_at ? "confirmed" : null);
  const pending = message.requires_confirmation && !resolved;

  return (
    <div className="flex items-start gap-2">
      <span
        aria-hidden
        className="mt-0.5 flex size-6 shrink-0 items-center justify-center rounded-lg bg-[var(--content-warning-soft)]"
      >
        <Zap strokeWidth={1.9} className="size-3.5 text-[var(--content-warning)]" />
      </span>
      <div className="min-w-0 flex-1 rounded-xl border border-[var(--content-warning)]/30 bg-[var(--content-warning-soft)] px-3 py-2.5 [overflow-wrap:anywhere]">
        <div className="flex flex-wrap items-center justify-between gap-x-2 gap-y-1">
          <p className="type-small font-semibold text-[var(--text-primary)]">{title}</p>
          {resolved === "confirmed" && (
            <StatusChip tone="success" size="sm" dot>
              {t("resolvedConfirmed")}
            </StatusChip>
          )}
          {resolved === "canceled" && (
            <StatusChip tone="neutral" size="sm" dot>
              {t("resolvedCanceled")}
            </StatusChip>
          )}
        </div>
        {message.content && (
          <p className="type-small mt-1 font-normal text-[var(--text-primary)]">
            {message.content}
          </p>
        )}
        {args.length > 0 && (
          <dl className="mt-2 space-y-1 rounded-lg bg-[var(--surface-card)]/60 px-2.5 py-2">
            {args.slice(0, 8).map(([key, value]) => (
              <div key={key} className="flex items-baseline gap-2">
                <dt className="type-caption w-28 shrink-0 truncate font-medium text-[var(--text-muted)]">
                  {t.has(`args.${key}`) ? t(`args.${key}`) : prettifyKey(key)}
                </dt>
                <dd className="type-caption min-w-0 flex-1 font-normal text-[var(--text-primary)] [overflow-wrap:anywhere]">
                  {formatArgValue(value)}
                </dd>
              </div>
            ))}
          </dl>
        )}
        {pending && (
          <div className="mt-2.5 flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={onConfirm}
              disabled={busy !== null}
              className="type-caption inline-flex items-center gap-1.5 rounded-full bg-[var(--content-warning)] px-3 py-1.5 font-semibold text-white outline-none transition hover:opacity-90 focus-visible:ring-2 focus-visible:ring-[var(--content-warning)]/40 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {busy === "confirm" && <Loader2 aria-hidden className="size-3 animate-spin" />}
              {busy === "confirm" ? t("confirmingAction") : t("confirmAction")}
            </button>
            <button
              type="button"
              onClick={onCancel}
              disabled={busy !== null}
              className="type-caption inline-flex items-center gap-1.5 rounded-full border border-[var(--border-default)] bg-[var(--surface-card)] px-3 py-1.5 font-semibold text-[var(--text-secondary)] outline-none transition-colors hover:bg-[var(--bg-muted)] hover:text-[var(--text-primary)] focus-visible:ring-2 focus-visible:ring-[var(--field-focus-border)] disabled:cursor-not-allowed disabled:opacity-60"
            >
              {busy === "cancel" && <Loader2 aria-hidden className="size-3 animate-spin" />}
              {busy === "cancel" ? t("cancelingAction") : t("confirmCancel")}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

/* --------------------------------- Streaming -------------------------------- */

export function StreamingBubble({ text, expanded }: { text: string; expanded: boolean }) {
  const wide = contentHasTable(text);
  return (
    <div className={cn("flex gap-2", wide ? "items-start" : "items-end")}>
      <AssistantAvatar />
      <div
        className={cn(
          "type-body min-w-0 rounded-2xl rounded-bl-sm border border-[var(--border-default)] bg-[var(--bg-subtle)] px-3 py-2.5 text-[var(--text-primary)] shadow-[var(--shadow-sm)] [overflow-wrap:anywhere] [word-break:break-word]",
          wide
            ? "w-full max-w-full flex-1"
            : expanded
              ? "max-w-[min(72ch,82%)]"
              : "max-w-[82%]",
        )}
      >
        <FormattedContent content={text} isUser={false} constrainText={expanded && wide} />
        {/* Blinking cursor */}
        <span className="ml-0.5 inline-block h-3.5 w-0.5 animate-pulse rounded-full bg-[var(--content-ai)] align-text-bottom" />
      </div>
    </div>
  );
}

/**
 * Animated, leak-safe "thinking/doing" line shown while the assistant works.
 * Renders ONLY the localized high-level phase text (`phase.*`) plus a subtle
 * pulse + 3-dot animation — never a raw tool/provider/model name. Unknown or
 * absent phase codes fall back to a generic "processing" label (AI_PRODUCT_SPEC
 * §9: no tool/provider/model internals surfaced to the user).
 */
export function PhaseIndicator({ phase }: { phase: string | null }) {
  const t = useTranslations("aiAssistant");
  const label = phase && t.has(`phase.${phase}`) ? t(`phase.${phase}`) : t("processing");
  return (
    <div className="flex items-end gap-2 self-start" aria-live="polite" aria-atomic="true">
      <AssistantAvatar />
      <div className="flex items-center gap-2 rounded-2xl rounded-bl-sm border border-[var(--content-ai)]/25 bg-[var(--content-ai-soft)] px-3.5 py-2.5 shadow-[var(--shadow-sm)]">
        {/* Keyed wrapper fades in on each phase change for a smooth transition. */}
        <span key={label} className="animate-in fade-in duration-300">
          <span className="type-small animate-pulse font-medium text-[var(--content-ai)]">
            {label}
          </span>
        </span>
        <span className="flex items-center gap-1" aria-hidden>
          {[0, 1, 2].map((i) => (
            <span
              key={i}
              className="size-1 animate-bounce rounded-full bg-[var(--content-ai)]/70"
              style={{ animationDelay: `${i * 0.15}s` }}
            />
          ))}
        </span>
      </div>
    </div>
  );
}
