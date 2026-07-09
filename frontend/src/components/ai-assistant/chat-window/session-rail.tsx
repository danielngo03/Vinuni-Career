"use client";

import { useMemo, useState } from "react";
import { useLocale } from "next-intl";
import { Plus, Search } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui";
import { SectionLabel } from "@/components/kit";
import type { ChatSession } from "@/lib/api";

export function SessionRail({
  sessions,
  activeId,
  loading,
  onNew,
  onSelect,
  t,
  className,
  showNewButton = true,
  searchable = false,
  showHeading = true,
}: {
  sessions: ChatSession[];
  activeId: string | null;
  loading: boolean;
  onNew: () => void;
  onSelect: (session: ChatSession) => void;
  t: (k: string) => string;
  className?: string;
  showNewButton?: boolean;
  searchable?: boolean;
  showHeading?: boolean;
}) {
  const locale = useLocale();
  const [query, setQuery] = useState("");
  const filteredSessions = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return sessions;
    return sessions.filter((session) =>
      (session.title || t("untitledSession")).toLowerCase().includes(needle),
    );
  }, [query, sessions, t]);

  return (
    <aside
      className={cn(
        "hidden min-h-0 flex-col border-r border-[var(--border-default)] bg-[var(--bg-subtle)] p-3 lg:flex",
        className,
      )}
    >
      {showNewButton && (
        <Button variant="primary" size="sm" fullWidth onClick={onNew}>
          <Plus aria-hidden strokeWidth={2} className="size-4" />
          {t("newChat")}
        </Button>
      )}

      {showHeading && (
        <SectionLabel className={cn("px-1", showNewButton ? "mt-4" : "mt-0")}>
          {t("sessions")}
        </SectionLabel>
      )}

      {searchable && (
        <label className={cn("relative block", showHeading ? "mt-2" : "mt-0")}>
          <span className="sr-only">{t("searchSessions")}</span>
          <Search
            aria-hidden
            strokeWidth={1.9}
            className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-[var(--text-muted)]"
          />
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder={t("searchSessions")}
            className="type-small h-8 w-full rounded-lg border border-[var(--border-default)] bg-[var(--surface-card)] pl-8 pr-2 text-[var(--text-primary)] outline-none transition-colors placeholder:text-[var(--text-muted)] focus:border-[var(--field-focus-border)]"
          />
        </label>
      )}

      <div className="mt-2 min-h-0 flex-1 overflow-y-auto pr-1">
        {loading ? (
          <div className="space-y-2">
            {[0, 1, 2].map((i) => (
              <div key={i} className="h-12 animate-skeleton rounded-lg bg-[var(--bg-muted)]" />
            ))}
          </div>
        ) : filteredSessions.length === 0 ? (
          <p className="type-small rounded-lg border border-dashed border-[var(--border-default)] bg-[var(--surface-card)] px-3 py-4 text-center leading-relaxed text-[var(--text-muted)]">
            {t("noSessions")}
          </p>
        ) : (
          <div className="space-y-1">
            {filteredSessions.map((session) => {
              const active = session.id === activeId;
              return (
                <button
                  key={session.id}
                  type="button"
                  aria-current={active ? "true" : undefined}
                  onClick={() => onSelect(session)}
                  className={cn(
                    "block w-full cursor-pointer rounded-lg px-3 py-2 text-left outline-none transition-colors focus-visible:ring-2 focus-visible:ring-[var(--field-focus-border)]",
                    active
                      ? "bg-[var(--bg-muted)] text-[var(--text-primary)] shadow-[inset_0_0_0_1px_var(--border-subtle)]"
                      : "text-[var(--text-primary)] hover:bg-[var(--bg-muted)]",
                  )}
                >
                  <span
                    className={cn(
                      "type-small block truncate",
                      active ? "font-semibold" : "font-medium",
                    )}
                  >
                    {session.title || t("untitledSession")}
                  </span>
                  <span className="type-caption mt-0.5 block truncate font-normal tabular-nums text-[var(--text-muted)]">
                    {formatSessionTime(session.last_message_at ?? session.created_at, locale)}
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

/** Relative session time ("5 minutes ago", "2 days ago"), locale-aware via Intl. */
function formatSessionTime(value: string | null, locale: string): string {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  const lang = locale === "vi" ? "vi" : "en";
  const diffMs = date.getTime() - Date.now();
  const abs = Math.abs(diffMs);
  const minute = 60_000;
  const hour = 3_600_000;
  const day = 86_400_000;

  try {
    const rtf = new Intl.RelativeTimeFormat(lang, { numeric: "auto" });
    if (abs < hour) return rtf.format(Math.round(diffMs / minute), "minute");
    if (abs < day) return rtf.format(Math.round(diffMs / hour), "hour");
    if (abs < 30 * day) return rtf.format(Math.round(diffMs / day), "day");
    return new Intl.DateTimeFormat(lang === "vi" ? "vi-VN" : "en-US", {
      month: "short",
      day: "numeric",
    }).format(date);
  } catch {
    return "";
  }
}
