"use client";

import { useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import { useQuery } from "@tanstack/react-query";
import {
  ArrowLeft,
  CaretDown,
  CheckCircle,
  ChartLineUp,
  Lightning,
  Minus,
  TrendDown,
  TrendUp,
  Trophy,
  WarningCircle,
} from "@phosphor-icons/react";
import { Skeleton } from "@/components/ui";
import { interviewPrepApi, type InterviewAttempt } from "@/lib/api";
import {
  interviewReadinessView,
  type ReadinessTone,
} from "@/lib/jobs/interview-readiness";
import { formatDateTime } from "@/lib/format";
import { cn } from "@/lib/utils";

/** Per-tone token classes (v9 Monochrome: green = ready, amber = developing). */
const TONE: Record<ReadinessTone, { bar: string; chip: string; text: string }> = {
  ok: {
    bar: "bg-[var(--teal-600)]",
    chip: "bg-[var(--teal-50)] text-[var(--teal-700)] border-[var(--teal-100)]",
    text: "text-[var(--teal-700)]",
  },
  progress: {
    bar: "bg-[var(--text-primary)]",
    chip: "bg-[var(--surface-secondary)] text-[var(--text-secondary)] border-[var(--border-default)]",
    text: "text-[var(--text-secondary)]",
  },
  low: {
    bar: "bg-[var(--amber-500)]",
    chip: "bg-[var(--amber-50)] text-[var(--amber-700)] border-[var(--amber-100)]",
    text: "text-[var(--amber-700)]",
  },
};

const TREND_ICON = {
  improving: TrendUp,
  steady: Minus,
  declining: TrendDown,
} as const;

/**
 * The student's "my interview progress / history" view. Renders the honest
 * deterministic readiness signal (band + trend + %), and past practice attempts.
 * In the `not_enough_data` state it shows "practise N more" — never a fabricated
 * readiness number. Never exposes provider/model/token/confidence internals.
 */
export function InterviewHistoryPanel({ onBack }: { onBack: () => void }) {
  const t = useTranslations("jobs.interviewSim");

  const history = useQuery({
    queryKey: ["interview", "history"],
    queryFn: () => interviewPrepApi.getHistory(),
    retry: false,
    staleTime: 30_000,
  });

  return (
    <div className="mx-auto max-w-2xl px-4 py-8 lg:py-10">
      <button
        type="button"
        onClick={onBack}
        className="mb-5 inline-flex items-center gap-1.5 text-xs font-semibold text-[var(--text-muted)] outline-none hover:text-[var(--text-secondary)] focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/30"
      >
        <ArrowLeft weight="bold" className="size-3.5" aria-hidden />
        {t("backToPractice")}
      </button>

      <div className="mb-6 flex items-start gap-2.5">
        <span className="flex size-9 shrink-0 items-center justify-center rounded-xl icon-chip-primary">
          <ChartLineUp aria-hidden weight="duotone" className="size-5" />
        </span>
        <div className="min-w-0">
          <h1 className="text-lg font-bold tracking-tight text-[var(--text-primary)]">
            {t("historyTitle")}
          </h1>
          <p className="mt-0.5 text-xs leading-relaxed text-[var(--text-muted)]">
            {t("historySubtitle")}
          </p>
        </div>
      </div>

      {history.isPending ? (
        <div className="space-y-3">
          <Skeleton className="h-28 w-full rounded-2xl" />
          <Skeleton className="h-20 w-full rounded-xl" />
          <Skeleton className="h-20 w-full rounded-xl" />
        </div>
      ) : history.isError ? (
        <div
          role="alert"
          className="flex flex-col items-start gap-3 rounded-2xl border border-[var(--border-default)] bg-[var(--surface-secondary)] px-4 py-4"
        >
          <p className="flex items-center gap-2 text-sm font-semibold text-[var(--text-primary)]">
            <WarningCircle aria-hidden weight="duotone" className="size-5 text-[var(--brand-red)]" />
            {t("historyErrorTitle")}
          </p>
          <p className="text-sm text-[var(--text-secondary)]">{t("historyErrorBody")}</p>
          <button
            type="button"
            onClick={() => void history.refetch()}
            className="rounded-lg border border-[var(--border-default)] px-3 py-1.5 text-xs font-semibold text-[var(--text-primary)] outline-none hover:bg-[var(--surface-hover)] focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/30"
          >
            {t("retry")}
          </button>
        </div>
      ) : (
        <div className="space-y-5">
          <ReadinessCard readiness={history.data.readiness} t={t} />
          <AttemptsList sessions={history.data.sessions} t={t} />
        </div>
      )}
    </div>
  );
}

function ReadinessCard({
  readiness,
  t,
}: {
  readiness: Parameters<typeof interviewReadinessView>[0];
  t: ReturnType<typeof useTranslations<"jobs.interviewSim">>;
}) {
  const view = interviewReadinessView(readiness);
  const tone = TONE[view.tone];

  return (
    <section className="marketplace-card rounded-2xl p-5" aria-label={t("readinessTitle")}>
      <div className="mb-3 flex items-center justify-between gap-3">
        <h2 className="flex items-center gap-1.5 text-xs font-bold uppercase tracking-wide text-[var(--text-muted)]">
          <Trophy aria-hidden weight="duotone" className="size-3.5" />
          {t("readinessTitle")}
        </h2>
        <span className="text-[11px] font-medium text-[var(--text-muted)]">
          {t("attemptsCount", { count: view.attempts })}
          {" · "}
          {t("answersCount", { count: readiness.answers_evaluated })}
        </span>
      </div>

      {view.hasSignal ? (
        <>
          <div className="flex items-end justify-between gap-3">
            <p className="text-2xl font-bold tabular-nums leading-none text-[var(--text-primary)]">
              {t("readinessPct", { pct: view.pct ?? 0 })}
            </p>
            <div className="flex items-center gap-2">
              {view.band && (
                <span
                  className={cn(
                    "inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-[11px] font-semibold",
                    tone.chip,
                  )}
                >
                  {view.tone === "ok" && <CheckCircle aria-hidden weight="fill" className="size-3.5" />}
                  {t(`band.${view.band}`)}
                </span>
              )}
              {view.trend && <TrendChip trend={view.trend} t={t} />}
            </div>
          </div>
          <div
            role="meter"
            aria-valuenow={view.pct ?? 0}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-label={t("readinessTitle")}
            className="mt-3 h-2 w-full overflow-hidden rounded-full bg-[var(--bg-muted)]"
          >
            <div
              className={cn("h-full rounded-full transition-[width] duration-500 motion-reduce:transition-none", tone.bar)}
              style={{ width: `${view.fillPct}%` }}
            />
          </div>
        </>
      ) : (
        // Honest low-data state — never a fabricated number.
        <div className="flex items-start gap-2.5 rounded-xl border border-[var(--border-default)] bg-[var(--surface-secondary)] px-3.5 py-3">
          <WarningCircle aria-hidden weight="duotone" className="mt-0.5 size-4 shrink-0 text-[var(--text-muted)]" />
          <div>
            <p className="text-sm font-semibold text-[var(--text-primary)]">
              {t("readinessNotEnoughTitle")}
            </p>
            <p className="mt-0.5 text-xs leading-relaxed text-[var(--text-secondary)]">
              {t("readinessNotEnoughBody", { count: view.answersNeeded })}
            </p>
          </div>
        </div>
      )}
    </section>
  );
}

function TrendChip({
  trend,
  t,
}: {
  trend: NonNullable<ReturnType<typeof interviewReadinessView>["trend"]>;
  t: ReturnType<typeof useTranslations<"jobs.interviewSim">>;
}) {
  const Icon = TREND_ICON[trend];
  const cls =
    trend === "improving"
      ? "text-[var(--teal-600)]"
      : trend === "declining"
        ? "text-[var(--amber-700)]"
        : "text-[var(--text-muted)]";
  return (
    <span className={cn("inline-flex items-center gap-1 text-[11px] font-semibold", cls)}>
      <Icon aria-hidden weight="bold" className="size-3.5" />
      {t(`trend.${trend}`)}
    </span>
  );
}

function AttemptsList({
  sessions,
  t,
}: {
  sessions: InterviewAttempt[];
  t: ReturnType<typeof useTranslations<"jobs.interviewSim">>;
}) {
  if (sessions.length === 0) {
    return (
      <div className="flex flex-col items-start gap-1.5 rounded-2xl border border-[var(--border-default)] bg-[var(--surface-secondary)] px-4 py-6">
        <p className="text-sm font-semibold text-[var(--text-primary)]">
          {t("historyEmptyTitle")}
        </p>
        <p className="text-sm text-[var(--text-secondary)]">{t("historyEmptyBody")}</p>
      </div>
    );
  }
  return (
    <section aria-label={t("attemptsTitle")}>
      <h2 className="mb-2 text-xs font-bold uppercase tracking-wide text-[var(--text-muted)]">
        {t("attemptsTitle")}
      </h2>
      <ul className="space-y-2">
        {sessions.map((s) => (
          <AttemptRow key={s.id} attempt={s} t={t} />
        ))}
      </ul>
    </section>
  );
}

function AttemptRow({
  attempt,
  t,
}: {
  attempt: InterviewAttempt;
  t: ReturnType<typeof useTranslations<"jobs.interviewSim">>;
}) {
  const locale = useLocale();
  const [open, setOpen] = useState(false);
  const detail = useQuery({
    queryKey: ["interview", "history", attempt.id],
    queryFn: () => interviewPrepApi.getSessionDetail(attempt.id),
    enabled: open,
    retry: false,
    staleTime: 60_000,
  });

  return (
    <li className="overflow-hidden rounded-xl border border-[var(--border-default)] bg-[var(--surface-card)]">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className="flex w-full items-center gap-3 px-3.5 py-3 text-left outline-none transition-colors hover:bg-[var(--surface-hover)] focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/30"
      >
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-semibold text-[var(--text-primary)]">
            {attempt.job_title || t("attemptUntitled")}
          </p>
          <p className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[11px] text-[var(--text-muted)]">
            <span>{formatDateTime(attempt.created_at, locale)}</span>
            <span aria-hidden>·</span>
            <span>{t("attemptAnswered", { answered: attempt.answered_count, total: attempt.questions_count })}</span>
          </p>
        </div>
        {attempt.avg_score !== null && (
          <span className="shrink-0 rounded-full bg-[var(--bg-subtle)] px-2 py-0.5 text-[11px] font-bold tabular-nums text-[var(--text-primary)]">
            {t("attemptAvg", { score: attempt.avg_score })}
          </span>
        )}
        <CaretDown
          aria-hidden
          weight="bold"
          className={cn("size-4 shrink-0 text-[var(--text-muted)] transition-transform", open && "rotate-180")}
        />
      </button>

      {open && (
        <div className="border-t border-[var(--border-default)] px-3.5 py-3">
          {detail.isPending ? (
            <div className="space-y-2">
              <Skeleton className="h-3 w-full rounded" />
              <Skeleton className="h-3 w-5/6 rounded" />
            </div>
          ) : detail.isError ? (
            <p className="text-xs text-[var(--text-secondary)]">{t("detailError")}</p>
          ) : detail.data.turns.length === 0 ? (
            <p className="text-xs text-[var(--text-muted)]">{t("attemptNoTurns")}</p>
          ) : (
            <ul className="space-y-2.5">
              {detail.data.turns.map((turn) => (
                <li key={turn.id} className="rounded-lg bg-[var(--bg-muted)] px-3 py-2">
                  <div className="flex items-start justify-between gap-2">
                    <p className="text-xs font-medium text-[var(--text-primary)]">{turn.question}</p>
                    {turn.score !== null && (
                      <span className="shrink-0 text-xs font-bold tabular-nums text-[var(--text-secondary)]">
                        {t("turnScore", { score: turn.score })}
                      </span>
                    )}
                  </div>
                  {turn.improve && (
                    <p className="mt-1 flex items-start gap-1.5 text-[11px] leading-relaxed text-[var(--text-secondary)]">
                      <Lightning aria-hidden weight="duotone" className="mt-0.5 size-3 shrink-0 text-[var(--amber-600)]" />
                      {turn.improve}
                    </p>
                  )}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </li>
  );
}
