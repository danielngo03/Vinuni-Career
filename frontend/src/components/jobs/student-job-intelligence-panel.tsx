"use client";

import { useEffect, useMemo, useState } from "react";
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
  Star,
  Target,
  WarningCircle,
} from "@phosphor-icons/react";
import { Link } from "@/i18n/navigation";
import { Button, Skeleton } from "@/components/ui";
import {
  ApiError,
  cvApi,
  jobsApi,
  type JobFit,
  type JobFitResult,
  type StudentCompetitionIntelligence,
  type StudentJobIntelligence,
} from "@/lib/api";
import { fitColor, fitTextColor, fitTier } from "@/lib/cv/fit";
import { rankByScore } from "@/lib/cv/fit";
import {
  usePrefersReducedMotion,
  useMountAnimation,
} from "@/lib/hooks/use-mount-animation";
import { cn } from "@/lib/utils";

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
 * The deterministic fit (score ring, 8 bands, matched/gaps) is sourced from the
 * fast per-CV `GET /cvs/job-fit` ranking so the student can inspect every CV's
 * own score client-side without a refetch. The slow AI narrative is fetched
 * separately via `GET /jobs/{job_id}/fit-explanation` after the panel renders.
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

  const intel = useQuery({
    queryKey: ["jobs", "student-intelligence", jobId],
    queryFn: () => jobsApi.studentIntelligence(jobId),
    retry: false,
    staleTime: 60_000,
  });

  // Per-CV ranking (all CVs + recommended id) — the deterministic fit source.
  const fit = useQuery({
    queryKey: ["jobs", "cv-job-fit", jobId],
    queryFn: () => cvApi.jobFit(jobId),
    retry: false,
    staleTime: 60_000,
  });

  // 404 on the intelligence endpoint means the job isn't visible to this
  // student — the surrounding page handles that; hide rather than double-report.
  if (
    intel.isError &&
    intel.error instanceof ApiError &&
    intel.error.isNotFound
  ) {
    return null;
  }

  const isPending = intel.isPending || fit.isPending;
  const isError = intel.isError || fit.isError || !intel.data || !fit.data;

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

      {isPending ? (
        <IntelSkeleton />
      ) : isError ? (
        <div
          role="alert"
          className="flex flex-col items-start gap-3 rounded-xl border border-[var(--glass-border-strong)] bg-[var(--glass-surface-light)] px-4 py-4 backdrop-blur-sm"
        >
          <p className="flex items-center gap-2 text-sm font-semibold text-[var(--text-primary)]">
            <WarningCircle aria-hidden weight="duotone" className="size-5 text-[var(--brand-red)]" />
            {t("studentIntel.errorTitle")}
          </p>
          <p className="text-sm text-[var(--text-secondary)]">{t("studentIntel.errorBody")}</p>
          <Button
            variant="secondary"
            size="sm"
            onClick={() => {
              void intel.refetch();
              void fit.refetch();
            }}
            disabled={intel.isFetching || fit.isFetching}
          >
            <ArrowClockwise aria-hidden weight="bold" className="size-4" />
          </Button>
        </div>
      ) : (
        <IntelBody data={intel.data!} fit={fit.data!} jobId={jobId} />
      )}
    </section>
  );
}

function IntelBody({
  data,
  fit,
  jobId,
}: {
  data: StudentJobIntelligence;
  fit: JobFit;
  jobId: string;
}) {
  const t = useTranslations("jobs");

  return (
    <div className="space-y-5">
      <FitSection fit={fit} jobId={jobId} noCvBlocked={!data.apply_readiness.has_active_cv} />

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

const BAND_ORDER = [
  "skills",
  "experience",
  "scope",
  "credentials",
  "soft_skills",
  "trajectory",
] as const;

function FitSection({
  fit,
  jobId,
  noCvBlocked,
}: {
  fit: JobFit;
  jobId: string;
  noCvBlocked: boolean;
}) {
  const t = useTranslations("jobs");
  const tf = useTranslations("cvFit");

  // Best-first ranking so the recommended CV leads and the selector reads
  // top-down. Recommended id comes straight from the backend ranking.
  const ranked = useMemo(() => rankByScore(fit.results), [fit.results]);
  const recommendedId = fit.recommended_cv_id ?? ranked[0]?.cv_id ?? null;

  const [selectedId, setSelectedId] = useState<string | null>(recommendedId);
  // If the ranking changes (refetch), keep a valid selection.
  useEffect(() => {
    setSelectedId((prev) =>
      prev && ranked.some((r) => r.cv_id === prev) ? prev : recommendedId,
    );
  }, [ranked, recommendedId]);

  const selected =
    ranked.find((r) => r.cv_id === selectedId) ??
    ranked.find((r) => r.cv_id === recommendedId) ??
    ranked[0] ??
    null;

  if (noCvBlocked || !selected) {
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

  const isRecommended = selected.cv_id === recommendedId;

  return (
    <div className="space-y-4">
      {/* Score-first: the big ring + which CV it belongs to. */}
      <div className="flex items-start gap-4">
        <ScoreRing score={selected.score} />
        <div className="min-w-0 flex-1 space-y-1.5">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-[var(--text-muted)]">
            {tf("recommendedCvLabel")}
          </p>
          <p
            className="truncate text-sm font-bold text-[var(--text-primary)]"
            title={selected.title}
          >
            {selected.title}
          </p>
          <span
            className="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-semibold"
            style={{ color: fitTextColor(selected.score), backgroundColor: "var(--bg-subtle)" }}
          >
            {tf(`tier.${fitTier(selected.score)}`)}
          </span>
          {isRecommended && (
            <span className="ml-1.5 inline-flex items-center gap-1 rounded-full bg-[var(--teal-50)] px-2 py-0.5 text-[11px] font-semibold text-[var(--teal-700)]">
              <Star aria-hidden weight="fill" className="size-3" />
              {tf("recommendedBadge")}
            </span>
          )}
        </div>
      </div>

      {/* Other CVs — each with its own score, selectable client-side. */}
      {ranked.length > 1 && (
        <CvSelector
          ranked={ranked}
          selectedId={selected.cv_id}
          recommendedId={recommendedId}
          onSelect={setSelectedId}
        />
      )}

      {/* Matched evidence for the selected CV. */}
      <div>
        <h3 className="mb-1.5 flex items-center gap-1.5 text-xs font-semibold text-[var(--text-primary)]">
          <CheckCircle aria-hidden weight="duotone" className="size-4 text-[var(--teal-600)]" />
          {t("studentIntel.matchedTitle")}
        </h3>
        {selected.matched_skills.length > 0 ? (
          <ul className="flex flex-wrap gap-1.5">
            {selected.matched_skills.map((s) => (
              <li key={s} className="rounded-full bg-[var(--teal-50)] px-2.5 py-0.5 text-xs font-medium text-[var(--teal-600)]">
                {s}
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-xs text-[var(--text-muted)]">{t("studentIntel.noMatched")}</p>
        )}
      </div>

      {/* The 6 core HR evaluation criteria the deterministic scorer produces —
          the same dimensions a recruiter weighs. Ordered by importance. */}
      <div className="grid grid-cols-2 gap-x-4 gap-y-2 text-xs">
        {BAND_ORDER.map((band, i) => (
          <BandMeter key={band} label={band} value={Math.round(selected.bands[band] ?? 0)} index={i} />
        ))}
      </div>

      {selected.gaps.length > 0 && (
        <div>
          <h3 className="mb-1.5 flex items-center gap-1.5 text-xs font-semibold text-[var(--text-primary)]">
            <span className="flex size-5 shrink-0 items-center justify-center rounded-md icon-chip-warning shadow-sm">
              <PlusCircle aria-hidden weight="duotone" className="size-3 text-white" />
            </span>
            {t("studentIntel.gapsTitle")}
          </h3>
          <ul className="flex flex-wrap gap-1.5">
            {selected.gaps.map((g) => (
              <li key={g} className="rounded-full border border-dashed border-[var(--amber-600)]/40 bg-[var(--amber-50)] px-2.5 py-0.5 text-xs font-medium text-[var(--amber-700)]">
                {g}
              </li>
            ))}
          </ul>
        </div>
      )}

      {selected.stale && (
        <p className="flex items-start gap-2 rounded-xl bg-[var(--amber-50)] px-3.5 py-2.5 text-xs leading-relaxed text-[var(--amber-700)]">
          <WarningCircle aria-hidden weight="duotone" className="mt-0.5 size-4 shrink-0" />
          {t("studentIntel.staleTitle")}
        </p>
      )}

      {/* Slow AI narrative — fetched after render, keyed to the selected CV. */}
      <AiAssessment jobId={jobId} cvId={selected.cv_id} />
    </div>
  );
}

/** Big total-score ring that animates its arc + number 0 → score on mount. */
function ScoreRing({ score }: { score: number }) {
  const tf = useTranslations("cvFit");
  const reduced = usePrefersReducedMotion();
  const animated = useMountAnimation(reduced);

  const CIRC = 138.23; // 2πr, r = 22
  const target = Math.max(0, Math.min(100, score));
  const shownArc = animated ? target : 0;
  const dash = (shownArc / 100) * CIRC;
  const color = fitColor(target);

  // Count-up number (0 → score) mirrors the arc when motion is allowed.
  const [display, setDisplay] = useState(reduced ? target : 0);
  useEffect(() => {
    if (reduced) {
      setDisplay(target);
      return;
    }
    const durationMs = 800;
    const start = performance.now();
    let raf = 0;
    const step = (now: number) => {
      const p = Math.min(1, (now - start) / durationMs);
      // ease-out cubic
      const eased = 1 - Math.pow(1 - p, 3);
      setDisplay(Math.round(eased * target));
      if (p < 1) raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [target, reduced]);

  return (
    <div className="shrink-0">
      <div
        className="relative size-16"
        role="meter"
        aria-valuenow={target}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={tf("scoreAria", { score: target })}
      >
        <svg viewBox="0 0 56 56" className="size-16 -rotate-90" aria-hidden>
          <circle cx="28" cy="28" r="22" fill="none" stroke="var(--bg-muted)" strokeWidth="5" />
          <circle
            cx="28"
            cy="28"
            r="22"
            fill="none"
            stroke={color}
            strokeWidth="5"
            strokeLinecap="round"
            strokeDasharray={`${dash} ${CIRC}`}
            style={{
              transition: reduced ? "none" : "stroke-dasharray 800ms cubic-bezier(0.22,1,0.36,1)",
            }}
          />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className="text-xl font-extrabold leading-none tabular-nums" style={{ color: fitTextColor(target) }}>
            {display}
          </span>
          <span className="text-[9px] font-semibold text-[var(--text-muted)]">/100</span>
        </div>
      </div>
    </div>
  );
}

/** Compact, keyboard-navigable list of the student's CVs, each with its score. */
function CvSelector({
  ranked,
  selectedId,
  recommendedId,
  onSelect,
}: {
  ranked: JobFitResult[];
  selectedId: string;
  recommendedId: string | null;
  onSelect: (id: string) => void;
}) {
  const tf = useTranslations("cvFit");
  return (
    <div>
      <p className="mb-1.5 text-[11px] font-semibold uppercase tracking-wide text-[var(--text-muted)]">
        {tf("otherTitle")}
      </p>
      <ul role="listbox" aria-label={tf("otherTitle")} className="space-y-1">
        {ranked.map((r) => {
          const isSelected = r.cv_id === selectedId;
          const isRecommended = r.cv_id === recommendedId;
          return (
            <li key={r.cv_id} role="option" aria-selected={isSelected}>
              <button
                type="button"
                onClick={() => onSelect(r.cv_id)}
                aria-label={tf("cvScoreAria", { title: r.title, score: r.score })}
                className={cn(
                  "flex w-full items-center gap-2 rounded-lg px-2.5 py-1.5 text-left outline-none transition-colors focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/30",
                  isSelected
                    ? "bg-[var(--glass-surface-light)] ring-1 ring-inset ring-[var(--glass-border-strong)]"
                    : "hover:bg-[var(--glass-surface-light)]",
                )}
              >
                <span
                  aria-hidden
                  className="flex size-6 shrink-0 items-center justify-center rounded-full text-[11px] font-bold tabular-nums"
                  style={{
                    color: fitTextColor(r.score),
                    backgroundColor: "var(--bg-subtle)",
                  }}
                >
                  {r.score}
                </span>
                <span className="min-w-0 flex-1 truncate text-xs font-medium text-[var(--text-primary)]" title={r.title}>
                  {r.title}
                </span>
                {isRecommended && (
                  <Star aria-hidden weight="fill" className="size-3 shrink-0 text-[var(--teal-600)]" />
                )}
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

function BandMeter({ label, value, index }: { label: string; value: number; index: number }) {
  const t = useTranslations("cvFit");
  const reduced = usePrefersReducedMotion();
  const animated = useMountAnimation(reduced);
  const width = animated ? Math.max(2, value) : 0;
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
          className="h-full rounded-full"
          style={{
            width: `${width}%`,
            backgroundColor: fitColor(value),
            transition: reduced
              ? "none"
              : "width 700ms cubic-bezier(0.22,1,0.36,1)",
            transitionDelay: reduced ? "0ms" : `${index * 45}ms`,
          }}
        />
      </div>
    </div>
  );
}

/**
 * Slow AI narrative for the selected CV, fetched AFTER the panel paints. Shows
 * a tasteful evaluating state while loading; hides entirely when no explanation
 * is available (AI offline, low-signal, error) — never dumps an error.
 */
function AiAssessment({ jobId, cvId }: { jobId: string; cvId: string }) {
  const tf = useTranslations("cvFit");
  const query = useQuery({
    queryKey: ["jobs", "fit-explanation", jobId, cvId],
    queryFn: () => jobsApi.fitExplanation(jobId, cvId),
    retry: false,
    staleTime: 60_000,
  });

  if (query.isPending || query.isFetching) {
    return (
      <div
        role="status"
        aria-live="polite"
        className="rounded-xl border border-[var(--glass-border)] bg-[var(--glass-surface-light)] px-3.5 py-3"
      >
        <p className="flex items-center gap-2 text-xs font-semibold text-[var(--text-primary)]">
          <Sparkle aria-hidden weight="duotone" className="size-4 animate-pulse text-[var(--brand-primary)]" />
          {tf("aiEvaluating")}
        </p>
        <p className="mt-1 text-[11px] leading-relaxed text-[var(--text-muted)]">
          {tf("aiEvaluatingHint")}
        </p>
        <div className="mt-2 space-y-1.5" aria-hidden>
          <Skeleton className="h-2.5 w-full rounded" />
          <Skeleton className="h-2.5 w-5/6 rounded" />
          <Skeleton className="h-2.5 w-2/3 rounded" />
        </div>
      </div>
    );
  }

  // No error dump: hide the section when unavailable.
  if (
    query.isError ||
    !query.data ||
    !query.data.ai_explanation_available ||
    !query.data.explanation
  ) {
    return null;
  }

  return (
    <div className="rounded-xl border border-[var(--glass-border)] bg-[var(--glass-surface-light)] px-3.5 py-3">
      <h3 className="mb-1.5 flex items-center gap-1.5 text-xs font-semibold text-[var(--text-primary)]">
        <Sparkle aria-hidden weight="duotone" className="size-4 text-[var(--brand-primary)]" />
        {tf("aiAssessmentTitle")}
      </h3>
      <p className="text-xs leading-relaxed text-[var(--text-secondary)] whitespace-pre-line">
        {query.data.explanation}
      </p>
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
        <Skeleton className="size-16 rounded-full" />
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
