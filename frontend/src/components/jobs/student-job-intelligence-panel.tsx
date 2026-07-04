"use client";

import { useTranslations } from "next-intl";
import { useQuery } from "@tanstack/react-query";
import {
  ArrowClockwise,
  ArrowUpRight,
  CheckCircle,
  Compass,
  FileText,
  Fire,
  ChartLineUp,
  PlusCircle,
  Sparkle,
  Target,
  WarningCircle,
} from "@phosphor-icons/react";
import { Link } from "@/i18n/navigation";
import { Button, Skeleton } from "@/components/ui";
import {
  ApiError,
  jobsApi,
  type StudentCompetitionIntelligence,
  type StudentFitLabel,
  type StudentJobFit,
  type StudentJobIntelligence,
} from "@/lib/api";
import { FIT_TIER_FILL, FIT_TIER_TEXT, type FitTier } from "@/lib/cv/fit";
import { cn } from "@/lib/utils";

function fitLabelTier(label: StudentFitLabel): FitTier {
  switch (label) {
    case "strong_fit":
      return "strong";
    case "good_fit":
      return "good";
    case "possible_fit":
      return "possible";
    default:
      return "weak";
  }
}

const COMPETITION_TONE: Record<
  NonNullable<StudentCompetitionIntelligence["label"]>,
  { badge: string; icon: typeof Fire }
> = {
  low: {
    badge: "bg-[var(--teal-50)] text-[var(--teal-700)] border border-[var(--teal-100)]",
    icon: ChartLineUp,
  },
  moderate: {
    badge: "bg-[var(--amber-50)] text-[var(--amber-700)] border border-[var(--amber-100)]",
    icon: ChartLineUp,
  },
  high: {
    badge: "bg-[var(--red-50)] text-[var(--red-600)] border border-[var(--red-100)]",
    icon: Fire,
  },
  very_high: {
    badge: "bg-[var(--red-100)] text-[var(--red-700)] border border-[var(--red-400)]",
    icon: Fire,
  },
};

/**
 * Combined, login-only student job intelligence panel: best-CV fit, bucketed
 * competition, learning gaps, and next actions from
 * `GET /jobs/{job_id}/student-intelligence` (docs/API_CONTRACTS.md §Student
 * Job Intelligence). This SUPERSEDES `CvFitPanel` + the public
 * `CompetitionBadge` for signed-in students — render only for authenticated
 * students; guests must never reach this (401/403 on the endpoint).
 *
 * Never renders provider/model/token/raw-confidence internals, other
 * applicants, exact ranks, or a hiring-probability guarantee.
 */
export function StudentJobIntelligencePanel({
  jobId,
  className,
}: {
  jobId: string;
  className?: string;
}) {
  const t = useTranslations("jobs");

  const query = useQuery({
    queryKey: ["jobs", "student-intelligence", jobId],
    queryFn: () => jobsApi.studentIntelligence(jobId),
    retry: false,
    staleTime: 60_000,
  });

  // 404 means the job isn't visible to this student — the surrounding page
  // already handles that; hide the panel rather than double-reporting.
  if (
    query.isError &&
    query.error instanceof ApiError &&
    query.error.isNotFound
  ) {
    return null;
  }

  return (
    <section
      aria-labelledby="student-job-intel-title"
      className={cn(
        "rounded-2xl border border-[var(--glass-border-strong)] bg-[var(--glass-surface)] backdrop-blur-md p-5",
        className,
      )}
    >
      <header className="mb-4 flex items-start gap-2.5">
        <span className="flex size-9 shrink-0 items-center justify-center rounded-xl icon-chip-primary shadow-sm">
          <Sparkle aria-hidden weight="duotone" className="size-5 text-white" />
        </span>
        <div className="min-w-0">
          <h2
            id="student-job-intel-title"
            className="text-base font-bold tracking-tight text-[var(--text-primary)]"
          >
            {t("studentIntel.panelTitle")}
          </h2>
          <p className="mt-0.5 text-xs leading-relaxed text-[var(--text-muted)]">
            {t("studentIntel.panelSubtitle")}
          </p>
        </div>
      </header>

      {query.isPending ? (
        <IntelSkeleton />
      ) : query.isError || !query.data ? (
        <div
          role="alert"
          className="flex flex-col items-start gap-3 rounded-xl border border-[var(--glass-border-strong)] bg-[var(--glass-surface-light)] px-4 py-4 backdrop-blur-sm"
        >
          <p className="flex items-center gap-2 text-sm font-semibold text-[var(--text-primary)]">
            <WarningCircle aria-hidden weight="duotone" className="size-5 text-[var(--brand-red)]" />
            {t("studentIntel.errorTitle")}
          </p>
          <p className="text-sm text-[var(--text-secondary)]">{t("studentIntel.errorBody")}</p>
          <Button variant="secondary" size="sm" onClick={() => query.refetch()} disabled={query.isFetching}>
            <ArrowClockwise aria-hidden weight="bold" className="size-4" />
          </Button>
        </div>
      ) : (
        <IntelBody data={query.data} jobId={jobId} />
      )}
    </section>
  );
}

function IntelBody({ data, jobId }: { data: StudentJobIntelligence; jobId: string }) {
  const t = useTranslations("jobs");
  return (
    <div className="space-y-5">
      <FitSection fit={data.fit} />

      <div className="border-t border-[var(--glass-border)] pt-4">
        <h3 className="mb-2.5 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-[var(--text-muted)]">
          <Target aria-hidden weight="duotone" className="size-3.5" />
          {t("studentIntel.competitionTitle")}
        </h3>
        <CompetitionSection competition={data.competition} />
      </div>

      {data.learning_gaps.length > 0 && (
        <div className="border-t border-[var(--glass-border)] pt-4">
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-[var(--text-muted)]">
            {t("studentIntel.learningGapsTitle")}
          </h3>
          <ul className="space-y-2">
            {data.learning_gaps.map((gap) => (
              <li key={gap.skill} className="rounded-xl bg-[var(--glass-surface-light)] px-3 py-2 text-xs">
                <span className="font-semibold text-[var(--text-primary)]">{gap.skill}</span>
                <p className="mt-0.5 leading-relaxed text-[var(--text-secondary)]">{gap.suggestion}</p>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="border-t border-[var(--glass-border)] pt-4">
        <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-[var(--text-muted)]">
          {t("studentIntel.nextActionsTitle")}
        </h3>
        <NextActions data={data} jobId={jobId} />
      </div>
    </div>
  );
}

function FitSection({ fit }: { fit: StudentJobFit }) {
  const t = useTranslations("jobs");

  if (fit.status === "no_active_cv" || fit.score === null || fit.bands === null) {
    return (
      <div className="flex flex-col items-start gap-3 rounded-xl border border-[var(--glass-border-strong)] bg-[var(--glass-surface-light)] px-4 py-5 backdrop-blur-sm">
        <p className="flex items-center gap-2 text-sm font-semibold text-[var(--text-primary)]">
          <FileText aria-hidden weight="duotone" className="size-5 text-[var(--text-muted)]" />
          {t("studentIntel.fitNoCvTitle")}
        </p>
        <p className="text-sm text-[var(--text-secondary)]">{t("studentIntel.fitNoCvBody")}</p>
        <Link href="/student/cv">
          <Button variant="primary" size="sm">
            {t("studentIntel.createCv")}
          </Button>
        </Link>
      </div>
    );
  }

  const tier = fitLabelTier(fit.label ?? "weak_fit");
  const CIRC = 138.23;
  const dash = (fit.score / 100) * CIRC;

  return (
    <div className="space-y-4">
      <div className="flex items-start gap-4">
        <div className="shrink-0 text-center">
          <div className="relative size-16" aria-label={`${fit.score}/100`}>
            <svg viewBox="0 0 56 56" className="size-16 -rotate-90" aria-hidden>
              <circle cx="28" cy="28" r="22" fill="none" stroke="var(--bg-muted)" strokeWidth="5" />
              <circle
                cx="28"
                cy="28"
                r="22"
                fill="none"
                stroke={FIT_TIER_FILL[tier]}
                strokeWidth="5"
                strokeLinecap="round"
                strokeDasharray={`${dash} ${CIRC}`}
                className="transition-[stroke-dasharray] duration-700 motion-reduce:transition-none"
              />
            </svg>
            <div className="absolute inset-0 flex flex-col items-center justify-center">
              <span className="text-xl font-extrabold leading-none tabular-nums" style={{ color: FIT_TIER_TEXT[tier] }}>
                {fit.score}
              </span>
              <span className="text-[9px] font-semibold text-[var(--text-muted)]">/100</span>
            </div>
          </div>
          <span
            className="mt-1.5 inline-block rounded-full px-2 py-0.5 text-[11px] font-semibold"
            style={{ color: FIT_TIER_TEXT[tier], backgroundColor: "var(--bg-subtle)" }}
          >
            {t(`studentIntel.fitLabel.${fit.label ?? "weak_fit"}`)}
          </span>
        </div>
        <div className="min-w-0 flex-1 space-y-2.5">
          <div>
            <h3 className="mb-1.5 flex items-center gap-1.5 text-xs font-semibold text-[var(--text-primary)]">
              <CheckCircle aria-hidden weight="duotone" className="size-4 text-[var(--teal-600)]" />
              {t("studentIntel.matchedTitle")}
            </h3>
            {fit.matched_evidence.length > 0 ? (
              <ul className="flex flex-wrap gap-1.5">
                {fit.matched_evidence.map((s) => (
                  <li key={s} className="rounded-full bg-[var(--teal-50)] px-2.5 py-0.5 text-xs font-medium text-[var(--teal-600)]">
                    {s}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-xs text-[var(--text-muted)]">{t("studentIntel.noMatched")}</p>
            )}
          </div>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-x-4 gap-y-2 text-xs">
        <BandMeter label="skills" value={fit.bands.skills} />
        <BandMeter label="experience" value={fit.bands.experience} />
        <BandMeter label="logistics" value={fit.bands.logistics} />
        <BandMeter label="quality" value={fit.bands.quality} />
      </div>

      {fit.gaps.length > 0 && (
        <div>
          <h3 className="mb-1.5 flex items-center gap-1.5 text-xs font-semibold text-[var(--text-primary)]">
            <span className="flex size-5 shrink-0 items-center justify-center rounded-md icon-chip-warning shadow-sm">
              <PlusCircle aria-hidden weight="duotone" className="size-3 text-white" />
            </span>
            {t("studentIntel.gapsTitle")}
          </h3>
          <ul className="flex flex-wrap gap-1.5">
            {fit.gaps.map((g) => (
              <li key={g} className="rounded-full border border-dashed border-[var(--amber-600)]/40 bg-[var(--amber-50)] px-2.5 py-0.5 text-xs font-medium text-[var(--amber-700)]">
                {g}
              </li>
            ))}
          </ul>
        </div>
      )}

      {fit.improvement_actions.length > 0 && (
        <div>
          <h3 className="mb-1.5 text-xs font-semibold text-[var(--text-primary)]">
            {t("studentIntel.improvementsTitle")}
          </h3>
          <ul className="space-y-1">
            {fit.improvement_actions.map((action) => (
              <li key={action} className="flex items-start gap-1.5 text-xs leading-relaxed text-[var(--text-secondary)]">
                <span className="mt-1.5 size-1 shrink-0 rounded-full bg-[var(--text-muted)]" />
                {action}
              </li>
            ))}
          </ul>
        </div>
      )}

      {fit.stale && (
        <p className="flex items-start gap-2 rounded-xl bg-[var(--amber-50)] px-3.5 py-2.5 text-xs leading-relaxed text-[var(--amber-700)]">
          <WarningCircle aria-hidden weight="duotone" className="mt-0.5 size-4 shrink-0" />
          {t("studentIntel.staleTitle")}
        </p>
      )}
    </div>
  );
}

function BandMeter({ label, value }: { label: string; value: number }) {
  const t = useTranslations("cvFit");
  const tier: FitTier = value >= 85 ? "strong" : value >= 70 ? "good" : value >= 50 ? "possible" : "weak";
  return (
    <div>
      <div className="mb-1 flex items-center justify-between gap-2">
        <span className="text-[11px] font-medium text-[var(--text-secondary)]">
          {t(`bands.${label}` as "bands.skills")}
        </span>
        <span className="text-[11px] font-semibold tabular-nums text-[var(--text-primary)]">{value}</span>
      </div>
      <div
        role="meter"
        aria-valuenow={value}
        aria-valuemin={0}
        aria-valuemax={100}
        className="h-1.5 w-full overflow-hidden rounded-full bg-[var(--bg-muted)]"
      >
        <div
          className="h-full rounded-full transition-[width] duration-500 motion-reduce:transition-none"
          style={{ width: `${Math.max(2, value)}%`, backgroundColor: FIT_TIER_FILL[tier] }}
        />
      </div>
    </div>
  );
}

function CompetitionSection({ competition }: { competition: StudentCompetitionIntelligence }) {
  const t = useTranslations("jobs");
  const tone = competition.label ? COMPETITION_TONE[competition.label] : null;
  const Icon = tone?.icon ?? ChartLineUp;

  return (
    <div className="space-y-3">
      {competition.signal === "low_signal" || !competition.label ? (
        <p className="flex items-start gap-2 rounded-xl bg-[var(--amber-50)] px-3.5 py-2.5 text-xs leading-relaxed text-[var(--amber-700)]">
          <WarningCircle aria-hidden weight="duotone" className="mt-0.5 size-4 shrink-0" />
          {t("studentIntel.lowSignalNote")}
        </p>
      ) : (
        <span className={cn("inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-semibold", tone?.badge)}>
          <Icon aria-hidden weight="duotone" className="size-3.5" />
          {t(`studentIntel.competitionLabel.${competition.label}`)}
        </span>
      )}

      <dl className="grid grid-cols-1 gap-1.5 text-xs text-[var(--text-secondary)]">
        <div className="flex items-center justify-between gap-2">
          <dt className="text-[var(--text-muted)]">{t("headcount")}</dt>
          <dd className="font-medium">{t(`studentIntel.seatsBucket.${competition.seats_bucket}`)}</dd>
        </div>
        <div className="flex items-center justify-between gap-2">
          <dt className="text-[var(--text-muted)]">{t("studentIntel.competitionTitle")}</dt>
          <dd className="font-medium">
            {t(`studentIntel.applicationVolumeBucket.${competition.application_volume_bucket}`)}
          </dd>
        </div>
        <div className="flex items-center justify-between gap-2">
          <dt className="text-[var(--text-muted)]">{t("deadline")}</dt>
          <dd className="font-medium">
            {t(`studentIntel.deadlineFreshness.${competition.deadline_freshness}`)}
          </dd>
        </div>
      </dl>

      {competition.guidance.length > 0 && (
        <div>
          <h4 className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-[var(--text-muted)]">
            {t("studentIntel.guidanceTitle")}
          </h4>
          <ul className="space-y-1">
            {competition.guidance.map((line) => (
              <li key={line} className="flex items-start gap-1.5 text-xs leading-relaxed text-[var(--text-secondary)]">
                <span className="mt-1.5 size-1 shrink-0 rounded-full bg-[var(--text-muted)]" />
                {line}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function NextActions({ data, jobId }: { data: StudentJobIntelligence; jobId: string }) {
  const t = useTranslations("jobs");
  return (
    <ul className="space-y-2">
      {data.next_actions.map((action, i) => {
        if (action.action === "select_best_cv" || action.action === "improve_cv") {
          const cvId = action.cv_id ?? data.best_cv_id ?? data.selected_cv_id;
          if (!cvId) return null;
          return (
            <li key={`${action.action}-${i}`}>
              <Link
                href={`/student/cv/${cvId}?job=${jobId}`}
                className="flex items-center justify-between gap-2 rounded-lg px-2 py-1.5 text-xs font-semibold text-[var(--brand-primary)] outline-none transition-colors hover:bg-[var(--glass-surface-light)] focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/30"
              >
                {t(`studentIntel.action.${action.action}`)}
                <ArrowUpRight aria-hidden weight="bold" className="size-3.5 shrink-0" />
              </Link>
            </li>
          );
        }
        if (action.action === "apply") {
          return (
            <li key={`apply-${i}`} className="flex items-start gap-1.5 text-xs leading-relaxed text-[var(--text-secondary)]">
              <span className="mt-1.5 size-1 shrink-0 rounded-full bg-[var(--text-muted)]" />
              {data.apply_readiness.blocked_reason === "already_applied"
                ? t("studentIntel.alreadyApplied")
                : data.apply_readiness.blocked_reason === "deadline_passed"
                  ? t("studentIntel.deadlinePassed")
                  : data.apply_readiness.blocked_reason === "no_active_cv"
                    ? t("studentIntel.noActiveCvBlocked")
                    : t(`studentIntel.action.${action.action}`)}
            </li>
          );
        }
        return (
          <li key={`${action.action}-${i}`} className="flex items-start gap-1.5 text-xs leading-relaxed text-[var(--text-secondary)]">
            <Compass aria-hidden weight="duotone" className="mt-0.5 size-3.5 shrink-0 text-[var(--text-muted)]" />
            {t(`studentIntel.action.${action.action}`)}
          </li>
        );
      })}
    </ul>
  );
}

function IntelSkeleton() {
  return (
    <div className="space-y-4">
      <div className="flex items-start gap-4">
        <Skeleton className="size-16 rounded-xl" />
        <div className="flex-1 space-y-2">
          <Skeleton className="h-4 w-2/3" />
          <Skeleton className="h-3 w-1/2" />
        </div>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <Skeleton className="h-6 w-full" />
        <Skeleton className="h-6 w-full" />
      </div>
      <Skeleton className="h-16 w-full" />
    </div>
  );
}
