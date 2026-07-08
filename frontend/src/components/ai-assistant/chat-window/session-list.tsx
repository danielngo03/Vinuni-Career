"use client";

import { ChatsCircle, Plus, Spinner, Trash } from "@phosphor-icons/react";
import { cn } from "@/lib/utils";
import type { ChatSession } from "@/lib/api";

export interface SessionListProps {
  sessions: ChatSession[];
  activeId: string | null;
  loading: boolean;
  /** Session id whose archive request is in flight (shows a spinner). */
  deletingId: string | null;
  /** Session id whose row is showing the inline delete confirmation. */
  confirmDeleteId: string | null;
  onNew: () => void;
  onSelect: (session: ChatSession) => void;
  /** Trash clicked — arm the inline confirmation for this row. */
  onRequestDelete: (id: string) => void;
  onCancelDelete: () => void;
  /** Confirm clicked — actually archive this session. */
  onConfirmDelete: (id: string) => void;
  t: (key: string, values?: Record<string, string | number>) => string;
}

/**
 * Reusable conversation-history list: a "new chat" action, a section label, and
 * the session rows. Each row can be selected or deleted (archived) via an inline
 * confirmation so no nested dialog is needed — this keeps focus inside the list
 * for both the persistent desktop rail and the mobile/collapsed overlay.
 *
 * Titles are display-only (rename/edit is a later backend round). Session
 * timestamps and titles are the only fields shown — never provider/model/token
 * internals (AI_PRODUCT_SPEC §9).
 */
export function SessionList({
  sessions,
  activeId,
  loading,
  deletingId,
  confirmDeleteId,
  onNew,
  onSelect,
  onRequestDelete,
  onCancelDelete,
  onConfirmDelete,
  t,
}: SessionListProps) {
  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <button
        type="button"
        onClick={onNew}
        className="inline-flex cursor-pointer items-center justify-center gap-2 rounded-xl bg-[var(--brand-primary)] px-3 py-2 text-sm font-semibold text-white outline-none transition-colors hover:bg-[var(--brand-primary)]/90 focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/35"
      >
        <Plus aria-hidden weight="bold" className="size-4" />
        {t("newChat")}
      </button>

      <div className="mt-4 flex items-center gap-2 px-1 text-[11px] font-bold uppercase tracking-wide text-[var(--text-muted)]">
        <ChatsCircle aria-hidden weight="duotone" className="size-4" />
        {t("sessions")}
      </div>

      <div className="mt-2 min-h-0 flex-1 overflow-y-auto pr-1">
        {loading ? (
          <div className="space-y-2">
            {[0, 1, 2].map((i) => (
              <div
                key={i}
                className="h-12 animate-pulse rounded-xl bg-[var(--glass-surface-light)]"
              />
            ))}
          </div>
        ) : sessions.length === 0 ? (
          <p className="rounded-xl border border-dashed border-[var(--border-default)] bg-[var(--glass-surface-light)] px-3 py-4 text-center text-xs leading-relaxed text-[var(--text-muted)]">
            {t("noSessions")}
          </p>
        ) : (
          <ul className="space-y-1.5">
            {sessions.map((session) => {
              const active = session.id === activeId;
              const confirming = session.id === confirmDeleteId;
              const deleting = session.id === deletingId;
              const title = session.title || t("untitledSession");

              if (confirming) {
                return (
                  <li key={session.id}>
                    <div className="flex items-center gap-1.5 rounded-xl border border-[var(--red-500)]/40 bg-[var(--red-50)] px-2.5 py-2">
                      <span className="min-w-0 flex-1 truncate text-xs font-medium text-[var(--red-700)]">
                        {t("deleteConfirm")}
                      </span>
                      <button
                        type="button"
                        onClick={onCancelDelete}
                        disabled={deleting}
                        className="shrink-0 rounded-md px-2 py-1 text-xs font-semibold text-[var(--text-secondary)] outline-none transition-colors hover:bg-[var(--bg-subtle)] focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/40 disabled:opacity-60"
                      >
                        {t("cancel")}
                      </button>
                      <button
                        type="button"
                        onClick={() => onConfirmDelete(session.id)}
                        disabled={deleting}
                        className="inline-flex shrink-0 items-center gap-1 rounded-md bg-[var(--brand-red)] px-2 py-1 text-xs font-semibold text-white outline-none transition-colors hover:bg-[var(--red-700)] focus-visible:ring-2 focus-visible:ring-[var(--brand-red)]/40 disabled:opacity-70"
                      >
                        {deleting ? (
                          <Spinner
                            aria-hidden
                            weight="bold"
                            className="size-3 animate-spin"
                          />
                        ) : (
                          <Trash aria-hidden weight="bold" className="size-3" />
                        )}
                        {t("delete")}
                      </button>
                    </div>
                  </li>
                );
              }

              return (
                <li key={session.id}>
                  <div
                    className={cn(
                      "group flex items-center rounded-xl transition-colors",
                      active
                        ? "bg-[var(--brand-primary)]"
                        : "hover:bg-[var(--glass-surface-heavy)]",
                    )}
                  >
                    <button
                      type="button"
                      onClick={() => onSelect(session)}
                      aria-current={active ? "true" : undefined}
                      className="flex min-w-0 flex-1 cursor-pointer flex-col items-start rounded-l-xl px-3 py-2 text-left outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-[var(--brand-primary)]/40"
                    >
                      <span
                        className={cn(
                          "block w-full truncate text-sm font-semibold",
                          active ? "text-white" : "text-[var(--text-primary)]",
                        )}
                      >
                        {title}
                      </span>
                      <span
                        className={cn(
                          "mt-0.5 block truncate text-[11px]",
                          active ? "text-white/72" : "text-[var(--text-muted)]",
                        )}
                      >
                        {formatSessionTime(
                          session.last_message_at ?? session.created_at,
                        )}
                      </span>
                    </button>
                    <button
                      type="button"
                      onClick={() => onRequestDelete(session.id)}
                      aria-label={t("deleteConversation", { title })}
                      title={t("deleteConversation", { title })}
                      className={cn(
                        "mr-1.5 shrink-0 rounded-lg p-1.5 outline-none transition-colors focus-visible:ring-2 focus-visible:ring-inset",
                        active
                          ? "text-white/70 hover:bg-white/15 hover:text-white focus-visible:ring-white/50"
                          : "text-[var(--text-muted)] hover:bg-[var(--red-50)] hover:text-[var(--red-600)] focus-visible:ring-[var(--red-500)]/50",
                      )}
                    >
                      <Trash aria-hidden weight="bold" className="size-4" />
                    </button>
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </div>
  );
}

function formatSessionTime(value: string | null): string {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}
