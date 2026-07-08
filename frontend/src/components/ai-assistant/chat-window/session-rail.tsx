"use client";

import { ChatsCircle, Plus } from "@phosphor-icons/react";
import { cn } from "@/lib/utils";
import type { ChatSession } from "@/lib/api";

export function SessionRail({
  sessions,
  activeId,
  loading,
  onNew,
  onSelect,
  t,
}: {
  sessions: ChatSession[];
  activeId: string | null;
  loading: boolean;
  onNew: () => void;
  onSelect: (session: ChatSession) => void;
  t: (k: string) => string;
}) {
  return (
    <aside className="hidden min-h-0 border-r border-[var(--glass-border)] bg-[var(--glass-surface-light)] p-3 lg:flex lg:flex-col">
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
          <div className="space-y-1.5">
            {sessions.map((session) => {
              const active = session.id === activeId;
              return (
                <button
                  key={session.id}
                  type="button"
                  onClick={() => onSelect(session)}
                  className={cn(
                    "block w-full cursor-pointer rounded-xl px-3 py-2 text-left outline-none transition-colors focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/30",
                    active
                      ? "bg-[var(--brand-primary)] text-white"
                      : "bg-[var(--glass-surface-light)] text-[var(--text-primary)] hover:bg-[var(--glass-surface-heavy)]",
                  )}
                >
                  <span className="block truncate text-sm font-semibold">
                    {session.title || t("untitledSession")}
                  </span>
                  <span
                    className={cn(
                      "mt-0.5 block truncate text-[11px]",
                      active ? "text-white/72" : "text-[var(--text-muted)]",
                    )}
                  >
                    {formatSessionTime(session.last_message_at ?? session.created_at)}
                  </span>
                </button>
              );
            })}
          </div>
        )}
      </div>
    </aside>
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
