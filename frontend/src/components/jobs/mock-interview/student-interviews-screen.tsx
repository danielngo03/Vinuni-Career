"use client";

import { useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowClockwise,
  ArrowLeft,
  CaretRight,
  ChatCircleDots,
  CheckCircle,
  ClockCountdown,
  Keyboard,
  Microphone,
  Target,
  TrendUp,
  WarningCircle,
} from "@phosphor-icons/react";
import { Link } from "@/i18n/navigation";
import { Button, EmptyState, Skeleton } from "@/components/ui";
import { PageHeader } from "@/components/layout/page-header";
import {
  mockInterviewApi,
  sessionListTitle,
  type MockInterviewModality,
  type MockInterviewProgress,
  type MockInterviewProgressTheme,
  type MockInterviewSessionListItem,
  type MockInterviewStatus,
} from "@/lib/api";
import { cn } from "@/lib/utils";
import { CoachingReport } from "./coaching-report";
import { FocusMix } from "./focus-mix";
import { TranscriptReview } from "./transcript-review";

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

const MODALITY_KEY: Record<MockInterviewModality, string> = {
  voice: "modalityVoice",
  text: "modalityText",
  realtime: "modalityRealtime",
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
 * Dedicated, cross-job "My interviews" surface. Lists every past mock-interview
 * session; a row opens a read-only review (coaching + transcript) for that
 * session. Real loading / empty / error states — never placeholders.
 */
export function StudentInterviewsScreen() {
  const [selectedId, setSelectedId] = useState<string | null>(null);

  if (selectedId) {
    return (
      <SessionReview
        sessionId={selectedId}
        onBack={() => setSelectedId(null)}
      />
    );
  }

  return <InterviewsList onOpen={setSelectedId} />;
}

/* -------------------------------- list ---------------------------------- */

function InterviewsList({ onOpen }: { onOpen: (id: string) => void }) {
  const t = useTranslations("jobs.mockInterview");
  const locale = useLocale();

  const query = useQuery({
    queryKey: ["mock-interview", "sessions", "all"],
    queryFn: () => mockInterviewApi.listSessions(),
    retry: false,
    staleTime: 30_000,
  });

  return (
    <>
      <PageHeader title={t("myInterviewsTitle")} />
      <p className="mb-5 -mt-2 text-sm text-[var(--text-secondary)]">
        {t("myInterviewsSubtitle")}
      </p>

      <div className="mx-auto max-w-3xl">
        <ProgressSummary />

        {query.isPending ? (
          <ul className="space-y-2.5" aria-hidden>
            {[0, 1, 2, 3].map((i) => (
              <li key={i}>
                <Skeleton className="h-[76px] w-full rounded-2xl" />
              </li>
            ))}
          </ul>
        ) : query.isError ? (
          <EmptyState
            kind="error"
            icon={WarningCircle}
            title={t("historyError")}
            action={
              <Button
                variant="secondary"
                onClick={() => query.refetch()}
                disabled={query.isFetching}
              >
                {t("historyRetry")}
              </Button>
            }
          />
        ) : query.data.length === 0 ? (
          <EmptyState
            kind="empty"
            icon={Microphone}
            title={t("myInterviewsEmptyTitle")}
            description={t("myInterviewsEmptyBody")}
            action={
              <Link href="/jobs">
                <Button variant="primary">
                  <Microphone aria-hidden weight="bold" className="size-4" />
                  {t("myInterviewsBrowseCta")}
                </Button>
              </Link>
            }
          />
        ) : (
          <section aria-labelledby="mi-sessions-title" className="mt-8">
            <div className="mb-3 flex items-baseline justify-between gap-3">
              <h2
                id="mi-sessions-title"
                className="text-sm font-bold text-[var(--text-primary)]"
              >
                {t("sessionsSectionTitle")}
              </h2>
              <p className="text-xs font-medium text-[var(--text-muted)]">
                {t("myInterviewsCount", { count: query.data.length })}
              </p>
            </div>
            <ul className="space-y-2.5">
              {query.data.map((item) => (
                <InterviewRow
                  key={item.id}
                  item={item}
                  locale={locale}
                  onOpen={onOpen}
                />
              ))}
            </ul>
          </section>
        )}
      </div>
    </>
  );
}

/* ------------------------------- progress ------------------------------- */

/**
 * Cross-session, score-free progress summary at the top of "My interviews":
 * completed count, qualitative themes to keep working on (recurring emphasized),
 * recurring strengths, and a focus mix. Never numbers-as-grades — the counts are
 * occurrence tallies, not scores. Real skeleton / empty / error states.
 */
function ProgressSummary() {
  const t = useTranslations("jobs.mockInterview");

  const query = useQuery({
    queryKey: ["mock-interview", "progress"],
    queryFn: () => mockInterviewApi.getProgress(),
    retry: false,
    staleTime: 30_000,
  });

  if (query.isPending) {
    return (
      <section
        className="mb-8 rounded-2xl border border-[var(--border-default)] bg-[var(--surface-card)] p-5 sm:p-6"
        aria-hidden
      >
        <Skeleton className="h-5 w-40 rounded" />
        <div className="mt-4 grid gap-5 sm:grid-cols-2">
          <Skeleton className="h-24 w-full rounded-xl" />
          <Skeleton className="h-24 w-full rounded-xl" />
        </div>
      </section>
    );
  }

  // Progress is a non-blocking header; on error offer a quiet retry and let the
  // session list below still render.
  if (query.isError) {
    return (
      <section className="mb-8 flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-[var(--border-default)] bg-[var(--surface-card)] px-5 py-4">
        <p className="text-sm text-[var(--text-muted)]">{t("progressError")}</p>
        <Button
          variant="secondary"
          size="sm"
          onClick={() => query.refetch()}
          disabled={query.isFetching}
        >
          {t("historyRetry")}
        </Button>
      </section>
    );
  }

  const progress = query.data;

  // Honest empty state — no completed sessions yet.
  if (progress.completed === 0) {
    return (
      <section className="mb-8 flex flex-col items-start gap-3 rounded-2xl border border-dashed border-[var(--border-strong)]/70 bg-[var(--surface-card)] p-5 sm:flex-row sm:items-center sm:gap-4 sm:p-6">
        <span
          aria-hidden
          className="flex size-11 shrink-0 items-center justify-center rounded-2xl icon-chip-primary"
        >
          <TrendUp weight="duotone" className="size-5" />
        </span>
        <div className="min-w-0 flex-1">
          <h2 className="text-base font-bold text-[var(--text-primary)]">
            {t("progressEmptyTitle")}
          </h2>
          <p className="mt-0.5 text-sm text-[var(--text-secondary)]">
            {t("progressEmptyBody")}
          </p>
        </div>
        <Link href="/jobs" className="shrink-0">
          <Button variant="primary" size="sm">
            <Microphone aria-hidden weight="bold" className="size-4" />
            {t("myInterviewsBrowseCta")}
          </Button>
        </Link>
      </section>
    );
  }

  return <ProgressSummaryCard progress={progress} />;
}

function ProgressSummaryCard({ progress }: { progress: MockInterviewProgress }) {
  const t = useTranslations("jobs.mockInterview");

  const focusLabel = (key: string): string => {
    const known: Record<string, string> = {
      technical: t("focusTechnical"),
      behavioral: t("focusBehavioral"),
      mixed: t("focusMixed"),
    };
    return known[key] ?? key;
  };

  return (
    <section
      aria-labelledby="mi-progress-title"
      className="mb-8 rounded-2xl border border-[var(--border-default)] bg-[var(--surface-card)] p-5 sm:p-6"
    >
      <header className="flex items-start justify-between gap-4">
        <div className="flex items-start gap-3">
          <span
            aria-hidden
            className="flex size-10 shrink-0 items-center justify-center rounded-2xl icon-chip-primary"
          >
            <TrendUp weight="duotone" className="size-5" />
          </span>
          <div className="min-w-0">
            <h2
              id="mi-progress-title"
              className="text-base font-bold tracking-tight text-[var(--text-primary)]"
            >
              {t("progressTitle")}
            </h2>
            <p className="mt-0.5 text-sm text-[var(--text-secondary)]">
              {t("progressSubtitle")}
            </p>
          </div>
        </div>
        <div className="shrink-0 text-right">
          <p className="text-3xl font-black leading-none tracking-tight tabular-nums text-[var(--text-primary)]">
            {progress.completed}
          </p>
          <p className="mt-1 text-xs font-medium text-[var(--text-secondary)]">
            {t("progressCompletedLabel")}
          </p>
        </div>
      </header>

      <div className="mt-5 grid gap-5 sm:grid-cols-2">
        <ThemeGroup
          icon={TrendUp}
          iconClass="text-[var(--amber-600)]"
          title={t("progressGapsTitle")}
          emptyLabel={t("progressGapsEmpty")}
          themes={progress.recurring_gaps}
          tone="gap"
        />
        <ThemeGroup
          icon={CheckCircle}
          iconClass="text-[var(--teal-600)]"
          title={t("progressStrengthsTitle")}
          emptyLabel={t("progressStrengthsEmpty")}
          themes={progress.top_strengths}
          tone="strength"
        />
      </div>

      <div className="mt-5 border-t border-[var(--border-subtle)] pt-4">
        <h3 className="mb-3 flex items-center gap-1.5 text-sm font-bold text-[var(--text-primary)]">
          <Target aria-hidden weight="duotone" className="size-4 text-[var(--text-secondary)]" />
          {t("progressFocusTitle")}
        </h3>
        <FocusMix
          data={progress.by_focus}
          labelFor={focusLabel}
          emptyLabel={t("progressFocusEmpty")}
        />
      </div>
    </section>
  );
}

function ThemeGroup({
  icon: Icon,
  iconClass,
  title,
  emptyLabel,
  themes,
  tone,
}: {
  icon: React.ElementType;
  iconClass: string;
  title: string;
  emptyLabel: string;
  themes: MockInterviewProgressTheme[];
  tone: "gap" | "strength";
}) {
  return (
    <div>
      <h3 className="mb-2.5 flex items-center gap-1.5 text-sm font-bold text-[var(--text-primary)]">
        <Icon aria-hidden weight="duotone" className={cn("size-4", iconClass)} />
        {title}
      </h3>
      {themes.length === 0 ? (
        <p className="text-sm text-[var(--text-muted)]">{emptyLabel}</p>
      ) : (
        <ul className="flex flex-wrap gap-2">
          {themes.map((theme, i) => (
            <ThemeChip key={i} theme={theme} tone={tone} />
          ))}
        </ul>
      )}
    </div>
  );
}

function ThemeChip({
  theme,
  tone,
}: {
  theme: MockInterviewProgressTheme;
  tone: "gap" | "strength";
}) {
  const t = useTranslations("jobs.mockInterview");
  const recurring = theme.recurring;

  const toneClass =
    tone === "gap"
      ? recurring
        ? "border-[var(--amber-600)]/45 bg-[var(--amber-50)] text-[var(--amber-700)] font-semibold"
        : "border-[var(--border-default)] bg-[var(--surface-card)] text-[var(--text-secondary)]"
      : recurring
        ? "border-[var(--teal-500)]/45 bg-[var(--teal-50)] text-[var(--teal-700)] font-semibold"
        : "border-[var(--border-default)] bg-[var(--surface-card)] text-[var(--text-secondary)]";

  return (
    <li
      className={cn(
        "inline-flex max-w-full items-center gap-1.5 rounded-full border px-3 py-1 text-xs",
        toneClass,
      )}
      title={
        recurring
          ? t("progressRecurringSeen", { count: theme.count })
          : t("progressSeen", { count: theme.count })
      }
    >
      {recurring && (
        <ArrowClockwise
          aria-hidden
          weight="bold"
          className="size-3 shrink-0"
        />
      )}
      <span className="truncate">{theme.text}</span>
      {theme.count > 1 && (
        <span
          className="shrink-0 tabular-nums opacity-70"
          aria-label={t("progressSeen", { count: theme.count })}
        >
          ×{theme.count}
        </span>
      )}
    </li>
  );
}

function InterviewRow({
  item,
  locale,
  onOpen,
}: {
  item: MockInterviewSessionListItem;
  locale: string;
  onOpen: (id: string) => void;
}) {
  const t = useTranslations("jobs.mockInterview");
  const status: MockInterviewStatus = STATUS_KEY[item.status]
    ? item.status
    : "completed";
  const ModalityIcon = MODALITY_ICON[item.modality] ?? ChatCircleDots;
  const title = sessionListTitle(item) || t("historyUntitled");
  const isActive = status === "active";
  const date = new Date(item.created_at).toLocaleDateString(
    locale === "vi" ? "vi-VN" : "en-US",
    { day: "numeric", month: "short", year: "numeric" },
  );

  // An in-progress session has no report yet — opening the review is a dead end.
  // Route it back into the live interview screen ("Resume") instead.
  const rowInner = (
    <>
        <span
          aria-hidden
          className="flex size-9 shrink-0 items-center justify-center rounded-xl icon-chip-primary"
        >
          <ModalityIcon weight="duotone" className="size-[18px]" />
        </span>
        <div className="min-w-0 flex-1">
          <p
            className="truncate text-sm font-semibold text-[var(--text-primary)]"
            title={title}
          >
            {title}
          </p>
          <div className="mt-1 flex flex-wrap items-center gap-x-2.5 gap-y-0.5 text-xs text-[var(--text-muted)]">
            <span>{date}</span>
            <span aria-hidden>·</span>
            <span className={cn("font-medium", STATUS_TONE[status])}>
              {t(STATUS_KEY[status])}
            </span>
            <span aria-hidden>·</span>
            <span>{t(MODALITY_KEY[item.modality] ?? "modalityText")}</span>
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
        <span
          className={cn(
            "hidden shrink-0 items-center gap-1 text-xs font-semibold sm:flex",
            isActive ? "text-[var(--teal-600)]" : "text-[var(--brand-primary)]",
          )}
        >
          {isActive ? t("resume") : t("historyView")}
          <CaretRight aria-hidden weight="bold" className="size-3.5" />
        </span>
    </>
  );

  if (isActive) {
    return (
      <li className="marketplace-card marketplace-card-hover flex items-center gap-1.5 rounded-2xl pr-2.5">
        <Link
          href={`/jobs/${item.job_id}/interview`}
          className="flex min-w-0 flex-1 items-center gap-3.5 rounded-2xl px-4 py-3.5 text-left outline-none focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/30"
        >
          {rowInner}
        </Link>
      </li>
    );
  }

  return (
    <li className="marketplace-card marketplace-card-hover flex items-center gap-1.5 rounded-2xl pr-2.5">
      <button
        type="button"
        onClick={() => onOpen(item.id)}
        className="flex min-w-0 flex-1 items-center gap-3.5 rounded-2xl px-4 py-3.5 text-left outline-none focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/30"
      >
        {rowInner}
      </button>
      <Link
        href={`/jobs/${item.job_id}/interview`}
        title={t("practiceAgain")}
        aria-label={`${t("practiceAgain")} — ${title}`}
        className="inline-flex shrink-0 items-center gap-1.5 rounded-full border border-[var(--border-strong)] px-3 py-1.5 text-xs font-semibold text-[var(--text-primary)] outline-none transition-colors hover:bg-[var(--bg-subtle)] hover:border-[var(--text-muted)] focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/30"
      >
        <ArrowClockwise aria-hidden weight="bold" className="size-3.5" />
        <span className="hidden sm:inline">{t("practiceAgain")}</span>
      </Link>
    </li>
  );
}

/* ------------------------------- detail --------------------------------- */

function SessionReview({
  sessionId,
  onBack,
}: {
  sessionId: string;
  onBack: () => void;
}) {
  const t = useTranslations("jobs.mockInterview");
  const qc = useQueryClient();

  const query = useQuery({
    queryKey: ["mock-interview", "session", sessionId],
    queryFn: () => mockInterviewApi.getSession(sessionId),
    retry: false,
  });

  function handleDeleted() {
    void qc.invalidateQueries({ queryKey: ["mock-interview", "sessions"] });
    onBack();
  }

  const backButton = (
    <button
      type="button"
      onClick={onBack}
      className="mb-4 inline-flex items-center gap-1.5 text-xs font-semibold text-[var(--text-muted)] outline-none transition-colors hover:text-[var(--text-secondary)] focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/30"
    >
      <ArrowLeft aria-hidden weight="bold" className="size-3.5" />
      {t("myInterviewsBackToList")}
    </button>
  );

  return (
    <div className="mx-auto max-w-2xl">
      {backButton}

      {query.isPending ? (
        <div
          className="flex min-h-[40vh] flex-col items-center justify-center gap-3"
          role="status"
        >
          <span
            aria-hidden
            className="size-8 animate-spin rounded-full border-4 border-[var(--bg-muted)] border-t-[var(--brand-primary)]"
          />
          <span className="sr-only">{t("connectingHint")}</span>
        </div>
      ) : query.isError ? (
        <EmptyState
          kind="error"
          icon={WarningCircle}
          title={t("myInterviewsDetailError")}
          action={
            <Button
              variant="secondary"
              onClick={() => query.refetch()}
              disabled={query.isFetching}
            >
              {t("historyRetry")}
            </Button>
          }
        />
      ) : (
        <div className="space-y-6">
          <CoachingReport
            report={query.data.report}
            coverage={query.data.coverage}
            jobId={query.data.job_id}
            jobTitle={query.data.job_title}
            completedAt={query.data.ended_at}
          />
          <TranscriptReview detail={query.data} onDeleted={handleDeleted} />
        </div>
      )}
    </div>
  );
}
