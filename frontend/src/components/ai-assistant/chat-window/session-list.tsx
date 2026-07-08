"use client";

import { useEffect, useRef, useState } from "react";
import {
  Check,
  ChatsCircle,
  PencilSimple,
  Plus,
  Spinner,
  Trash,
  X,
} from "@phosphor-icons/react";
import { cn } from "@/lib/utils";
import type { ChatSession } from "@/lib/api";

/** Server-enforced title bound (1..120 non-empty chars). */
const RENAME_MAX = 120;

export interface SessionListProps {
  sessions: ChatSession[];
  activeId: string | null;
  loading: boolean;
  /** Session id whose archive request is in flight (shows a spinner). */
  deletingId: string | null;
  /** Session id whose row is showing the inline delete confirmation. */
  confirmDeleteId: string | null;
  /** Session id whose row is in inline-rename edit mode. */
  renamingId: string | null;
  /** Session id whose rename request is in flight (shows a spinner). */
  savingRenameId: string | null;
  onNew: () => void;
  onSelect: (session: ChatSession) => void;
  /** Trash clicked — arm the inline confirmation for this row. */
  onRequestDelete: (id: string) => void;
  onCancelDelete: () => void;
  /** Confirm clicked — actually archive this session. */
  onConfirmDelete: (id: string) => void;
  /** Pencil clicked — swap this row into the inline rename editor. */
  onRequestRename: (id: string) => void;
  onCancelRename: () => void;
  /** Save clicked (or Enter) — persist the trimmed title for this session. */
  onSubmitRename: (id: string, title: string) => void;
  t: (key: string, values?: Record<string, string | number>) => string;
}

/**
 * Reusable conversation-history list: a "new chat" action, a section label, and
 * the session rows. Each row can be selected, renamed inline, or deleted
 * (archived) via an inline confirmation so no nested dialog is needed — this
 * keeps focus inside the list for both the persistent desktop rail and the
 * mobile/collapsed overlay.
 *
 * Rename swaps the title into a focused text input (Enter saves, Esc cancels)
 * with client-side 1..120 non-empty validation mirroring the server. Session
 * timestamps and titles are the only fields shown — never provider/model/token
 * internals (AI_PRODUCT_SPEC §9).
 */
export function SessionList({
  sessions,
  activeId,
  loading,
  deletingId,
  confirmDeleteId,
  renamingId,
  savingRenameId,
  onNew,
  onSelect,
  onRequestDelete,
  onCancelDelete,
  onConfirmDelete,
  onRequestRename,
  onCancelRename,
  onSubmitRename,
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
              const renaming = session.id === renamingId;
              const title = session.title || t("untitledSession");

              if (renaming) {
                return (
                  <li key={session.id}>
                    <SessionRenameRow
                      initialTitle={session.title ?? ""}
                      saving={session.id === savingRenameId}
                      onCancel={onCancelRename}
                      onSubmit={(next) => onSubmitRename(session.id, next)}
                      t={t}
                    />
                  </li>
                );
              }

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
                      onClick={() => onRequestRename(session.id)}
                      aria-label={t("renameConversation", { title })}
                      title={t("renameConversation", { title })}
                      className={cn(
                        "shrink-0 rounded-lg p-1.5 outline-none transition-colors focus-visible:ring-2 focus-visible:ring-inset",
                        active
                          ? "text-white/70 hover:bg-white/15 hover:text-white focus-visible:ring-white/50"
                          : "text-[var(--text-muted)] hover:bg-[var(--bg-subtle)] hover:text-[var(--text-primary)] focus-visible:ring-[var(--brand-primary)]/40",
                      )}
                    >
                      <PencilSimple aria-hidden weight="bold" className="size-4" />
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

/**
 * Inline rename editor swapped in place of a session row. Focuses + selects the
 * title on mount, saves on Enter or the Save button, and cancels on Esc or the
 * Cancel button. Save is blocked until the trimmed title is a non-empty
 * 1..120-char string, mirroring the server bound so the user never round-trips
 * an obviously-invalid value.
 */
function SessionRenameRow({
  initialTitle,
  saving,
  onCancel,
  onSubmit,
  t,
}: {
  initialTitle: string;
  saving: boolean;
  onCancel: () => void;
  onSubmit: (title: string) => void;
  t: (key: string, values?: Record<string, string | number>) => string;
}) {
  const [draft, setDraft] = useState(initialTitle);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const el = inputRef.current;
    if (el) {
      el.focus();
      el.select();
    }
  }, []);

  const trimmed = draft.trim();
  const valid = trimmed.length >= 1 && trimmed.length <= RENAME_MAX;

  function submit() {
    if (!valid || saving) return;
    onSubmit(trimmed);
  }

  return (
    <div className="flex items-center gap-1.5 rounded-xl border border-[var(--brand-primary)]/40 bg-[var(--glass-surface-heavy)] px-2 py-1.5">
      <input
        ref={inputRef}
        value={draft}
        maxLength={RENAME_MAX}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter") {
            e.preventDefault();
            submit();
          } else if (e.key === "Escape") {
            e.preventDefault();
            onCancel();
          }
        }}
        disabled={saving}
        aria-label={t("renameLabel")}
        className="min-w-0 flex-1 rounded-md border border-[var(--border-default)] bg-[var(--surface-card)] px-2 py-1 text-sm text-[var(--text-primary)] outline-none transition-colors focus-visible:border-[var(--brand-primary)]/60 focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/30 disabled:opacity-60"
      />
      <button
        type="button"
        onClick={onCancel}
        disabled={saving}
        aria-label={t("cancel")}
        title={t("cancel")}
        className="shrink-0 rounded-md p-1.5 text-[var(--text-secondary)] outline-none transition-colors hover:bg-[var(--bg-subtle)] focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/40 disabled:opacity-60"
      >
        <X aria-hidden weight="bold" className="size-4" />
      </button>
      <button
        type="button"
        onClick={submit}
        disabled={!valid || saving}
        aria-label={t("save")}
        title={t("save")}
        className="inline-flex shrink-0 items-center rounded-md bg-[var(--brand-primary)] p-1.5 text-white outline-none transition-colors hover:bg-[var(--brand-primary)]/90 focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/40 disabled:cursor-not-allowed disabled:opacity-60"
      >
        {saving ? (
          <Spinner aria-hidden weight="bold" className="size-4 animate-spin" />
        ) : (
          <Check aria-hidden weight="bold" className="size-4" />
        )}
      </button>
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
