"use client";

import { useLocale, useTranslations } from "next-intl";
import { useQuery } from "@tanstack/react-query";
import {
  CaretRight,
  ClockCountdown,
  Microphone,
  Keyboard,
  ChatCircleDots,
  WarningCircle,
} from "@phosphor-icons/react";
import { Button, Skeleton } from "@/components/ui";
import {
  mockInterviewApi,
  sessionListTitle,
  type MockInterviewModality,
  type MockInterviewSessionListItem,
  type MockInterviewStatus,
} from "@/lib/api";
import { cn } from "@/lib/utils";

const STATUS_KEY: Record<MockInterviewStatus, string> = {
  active: "statusActive",
  completed: "statusCompleted",
  aborted: "statusAborted",
  expired: "statusExpired",
};

const STATUS_TONE: Record<MockInterviewStatus, string> = {
  active: "text-[var(--amber-700)]",
  completed: "text-[var(--teal-700)]",
  aborted: "text-[var(--text-muted)]",
  expired: "text-[var(--text-muted)]",
};

const MODALITY_ICON: Record<MockInterviewModality, typeof Microphone> = {
  voice: Microphone,
  realtime: Microphone,
  text: Keyboard,
};

/** Format seconds as m:ss (locale-neutral data). */
function formatDuration(seconds: number | null): string {
  const s = Math.max(0, Math.round(seconds ?? 0));
  const m = Math.floor(s / 60);
  const rem = s % 60;
  return `${m}:${rem.toString().padStart(2, "0")}`;
}

/**
 * Recent mock-interview sessions. Clicking a row loads its coaching + transcript
 * for review. Renders real loading / empty / error states — never placeholders.
 */
export function InterviewHistory({
  onOpen,
  limit = 10,
}: {
  onOpen: (id: string) => void;
  limit?: number;
}) {
  const t = useTranslations("jobs.mockInterview");
  const locale = useLocale();

  const query = useQuery({
    queryKey: ["mock-interview", "sessions", limit],
    queryFn: () => mockInterviewApi.listSessions(limit),
    retry: false,
    staleTime: 30_000,
  });

  return (
    <section aria-labelledby="mi-history-title">
      <header className="mb-3">
        <h2
          id="mi-history-title"
          className="text-base font-bold tracking-tight text-[var(--text-primary)]"
        >
          {t("historyTitle")}
        </h2>
        <p className="mt-0.5 text-xs text-[var(--text-secondary)]">
          {t("historySubtitle")}
        </p>
      </header>

      {query.isPending ? (
        <ul className="space-y-2" aria-hidden>
          {[0, 1, 2].map((i) => (
            <li key={i}>
              <Skeleton className="h-16 w-full rounded-xl" />
            </li>
          ))}
        </ul>
      ) : query.isError ? (
        <div
          role="alert"
          className="flex flex-col items-start gap-2 rounded-xl border border-[var(--border-default)] bg-[var(--surface-card)] px-4 py-4"
        >
          <p className="flex items-center gap-2 text-sm font-semibold text-[var(--text-primary)]">
            <WarningCircle aria-hidden weight="duotone" className="size-5 text-[var(--brand-red)]" />
            {t("historyError")}
          </p>
          <Button variant="secondary" size="sm" onClick={() => query.refetch()} disabled={query.isFetching}>
            {t("historyRetry")}
          </Button>
        </div>
      ) : query.data.length === 0 ? (
        <div className="rounded-xl border border-dashed border-[var(--border-strong)]/60 bg-[var(--surface-card)]/60 px-5 py-8 text-center">
          <h3 className="text-sm font-semibold text-[var(--text-primary)]">
            {t("historyEmptyTitle")}
          </h3>
          <p className="mt-1 text-xs text-[var(--text-secondary)]">
            {t("historyEmptyBody")}
          </p>
        </div>
      ) : (
        <ul className="space-y-2">
          {query.data.map((item) => (
            <HistoryRow key={item.id} item={item} locale={locale} onOpen={onOpen} />
          ))}
        </ul>
      )}
    </section>
  );
}

function HistoryRow({
  item,
  locale,
  onOpen,
}: {
  item: MockInterviewSessionListItem;
  locale: string;
  onOpen: (id: string) => void;
}) {
  const t = useTranslations("jobs.mockInterview");
  const status: MockInterviewStatus = STATUS_KEY[item.status] ? item.status : "completed";
  const ModalityIcon = MODALITY_ICON[item.modality] ?? ChatCircleDots;
  const title = sessionListTitle(item) || t("historyUntitled");
  const date = new Date(item.created_at).toLocaleDateString(
    locale === "vi" ? "vi-VN" : "en-US",
    { day: "numeric", month: "short", year: "numeric" },
  );

  return (
    <li>
      <button
        type="button"
        onClick={() => onOpen(item.id)}
        className="marketplace-card marketplace-card-hover flex w-full items-center gap-3 rounded-xl px-4 py-3 text-left outline-none focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/30"
      >
        <span aria-hidden className="flex size-8 shrink-0 items-center justify-center rounded-lg icon-chip-primary">
          <ModalityIcon weight="duotone" className="size-4" />
        </span>
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-semibold text-[var(--text-primary)]" title={title}>
            {title}
          </p>
          <div className="mt-0.5 flex flex-wrap items-center gap-x-2.5 gap-y-0.5 text-xs text-[var(--text-muted)]">
            <span>{date}</span>
            <span aria-hidden>·</span>
            <span className={cn("font-medium", STATUS_TONE[status])}>{t(STATUS_KEY[status])}</span>
            {item.question_count > 0 && (
              <>
                <span aria-hidden>·</span>
                <span>{t("historyQuestions", { count: item.question_count })}</span>
              </>
            )}
            {item.duration_seconds != null && item.duration_seconds > 0 && (
              <>
                <span aria-hidden>·</span>
                <span className="inline-flex items-center gap-1 font-data">
                  <ClockCountdown aria-hidden weight="duotone" className="size-3.5" />
                  {formatDuration(item.duration_seconds)}
                </span>
              </>
            )}
          </div>
        </div>
        <span className="flex shrink-0 items-center gap-1 text-xs font-semibold text-[var(--brand-primary)]">
          {t("historyView")}
          <CaretRight aria-hidden weight="bold" className="size-3.5" />
        </span>
      </button>
    </li>
  );
}
