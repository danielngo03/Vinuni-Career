"use client";

import {
  ArrowSquareOut,
  Lightning,
  MagnifyingGlass,
  Sparkle,
  Spinner,
} from "@phosphor-icons/react";
import { cn } from "@/lib/utils";
import type { ChatMessage } from "@/lib/api";
import { TOOL_LABELS } from "./constants";

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
        <FormattedContent content={message.content} isUser={isUser} />
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

/** Render plain text with basic markdown: **bold**, lists, internal links. */
export function FormattedContent({
  content,
  isUser,
}: {
  content: string;
  isUser: boolean;
}) {
  const lines = content.split("\n").filter((l) => l.trim() !== "");

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
