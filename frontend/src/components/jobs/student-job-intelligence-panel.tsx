"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { useQuery } from "@tanstack/react-query";
import {
  ArrowClockwise,
  ArrowUpRight,
  CheckCircle,
  ChatCircleDots,
  MagnifyingGlassPlus,
  Sparkle,
  Target,
  WarningCircle,
} from "@phosphor-icons/react";
import { Link } from "@/i18n/navigation";
import { Button, Skeleton } from "@/components/ui";
import {
  ApiError,
  jobsApi,
  type StudentFitBands,
  type StudentJobIntelligence,
} from "@/lib/api";
import { fitColor, fitTextColor, fitTier } from "@/lib/cv/fit";
import {
  deriveCvReadiness,
  type CvReadiness,
} from "@/lib/jobs/job-intelligence";
import {
  usePrefersReducedMotion,
  useMountAnimation,
} from "@/lib/hooks/use-mount-animation";
import { cn } from "@/lib/utils";
import { AiEnergyHint } from "./ai-energy-hint";
import { AnalyzeCvDrawer } from "./analyze-cv-drawer";
import { CompetitionDrawer } from "./competition-drawer";
import { InterviewPrepPanel } from "./interview-prep-panel";

const BAND_ORDER = [
  "skills",
  "experience",
  "scope",
  "credentials",
  "soft_skills",
  "trajectory",
] as const;

type Tab = "fit" | "interview";

/**
 * Login-only student job intelligence panel (WS-4 / WS-14 / WS-15).
 *
 * SCORE-ONLY DEFAULT: a SINGLE `GET /jobs/{id}/student-intelligence` fetch
 * (deterministic, 0 model calls) drives the fit score ring + 6 bands + CV
 * readiness. The heavy, model-metered analysis and competition dashboards live
 * behind on-demand right-side drawers ("Analyze CV" / "Competition") that only
 * fetch when opened — no auto-fired overlapping queries on mount.
 *
 * Flat `marketplace-card` (v9 Monochrome, no glass/gradient), with the interview
 * prep folded into a second tab so the rail isn't two stacked AI panels. Never
 * renders provider/model/token/confidence internals, other applicants, exact
 * ranks, or a hiring-probability guarantee.
 */
export function StudentJobIntelligencePanel({
  jobId,
  className,
}: {
  jobId: string;
  className?: string;
}) {
  const t = useTranslations("jobs.studentIntel");
  const [tab, setTab] = useState<Tab>("fit");
  const [analyzeOpen, setAnalyzeOpen] = useState(false);
  const [competitionOpen, setCompetitionOpen] = useState(false);

  const intel = useQuery({
    queryKey: ["jobs", "student-intelligence", jobId],
    queryFn: () => jobsApi.studentIntelligence(jobId),
    retry: false,
    staleTime: 60_000,
  });

  // 404 = job not visible to this student; the page handles it — hide here.
  if (intel.isError && intel.error instanceof ApiError && intel.error.isNotFound) {
    return null;
  }

  return (
    <section
      aria-labelledby="student-job-intel-title"
      className={cn("marketplace-card overflow-hidden rounded-2xl", className)}
    >
      <header className="flex items-start gap-2.5 border-b border-[var(--border-default)] p-4 sm:p-5">
        <span className="flex size-9 shrink-0 items-center justify-center rounded-xl icon-chip-primary">
          <Sparkle aria-hidden weight="duotone" className="size-5" />
        </span>
        <div className="min-w-0">
          <h2 id="student-job-intel-title" className="text-base font-bold tracking-tight text-[var(--text-primary)]">
            {t("panelTitle")}
          </h2>
          <p className="mt-0.5 text-xs leading-relaxed text-[var(--text-muted)]">{t("panelSubtitle")}</p>
        </div>
      </header>

      {/* Progressive disclosure: fit vs. interview prep. */}
      <div role="tablist" aria-label={t("panelTitle")} className="flex gap-1 border-b border-[var(--border-default)] px-2 pt-2">
        <TabButton id="fit" active={tab === "fit"} onClick={() => setTab("fit")} icon={Target} label={t("tabFit")} />
        <TabButton id="interview" active={tab === "interview"} onClick={() => setTab("interview")} icon={ChatCircleDots} label={t("tabInterview")} />
      </div>

      <div className="p-4 sm:p-5">
        {tab === "fit" ? (
          intel.isPending ? (
            <FitSkeleton />
          ) : intel.isError || !intel.data ? (
            <ErrorBlock
              onRetry={() => void intel.refetch()}
              disabled={intel.isFetching}
            />
          ) : (
            <FitTab
              data={intel.data}
              onAnalyze={() => setAnalyzeOpen(true)}
              onCompetition={() => setCompetitionOpen(true)}
            />
          )
        ) : (
          <div role="tabpanel" aria-labelledby="tab-interview">
            <InterviewPrepPanel jobId={jobId} />
          </div>
        )}
      </div>

      {/* On-demand drawers — fetch ONLY when open. */}
      {intel.data && (
        <>
          <AnalyzeCvDrawer
            open={analyzeOpen}
            onClose={() => setAnalyzeOpen(false)}
            jobId={jobId}
            learningGaps={intel.data.learning_gaps}
            bestCvId={intel.data.best_cv_id}
          />
          <CompetitionDrawer
            open={competitionOpen}
            onClose={() => setCompetitionOpen(false)}
            jobId={jobId}
            competition={intel.data.competition}
          />
        </>
      )}
    </section>
  );
}

function TabButton({
  id,
  active,
  onClick,
  icon: Icon,
  label,
}: {
  id: string;
  active: boolean;
  onClick: () => void;
  icon: React.ElementType;
  label: string;
}) {
  return (
    <button
      type="button"
      role="tab"
      id={`tab-${id}`}
      aria-selected={active}
      onClick={onClick}
      className={cn(
        "flex items-center gap-1.5 rounded-t-lg border-b-2 px-3 py-2 text-xs font-semibold outline-none transition-colors focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/30",
        active
          ? "border-[var(--brand-primary)] text-[var(--text-primary)]"
          : "border-transparent text-[var(--text-muted)] hover:text-[var(--text-secondary)]",
      )}
    >
      <Icon aria-hidden weight="duotone" className="size-4" />
      {label}
    </button>
  );
}

function FitTab({
  data,
  onAnalyze,
  onCompetition,
}: {
  data: StudentJobIntelligence;
  onAnalyze: () => void;
  onCompetition: () => void;
}) {
  const t = useTranslations("jobs.studentIntel");
  const readiness = deriveCvReadiness(data.fit, data.apply_readiness);

  if (data.fit.status === "no_active_cv" || !data.apply_readiness.has_active_cv) {
    return (
      <div role="tabpanel" aria-labelledby="tab-fit" className="flex flex-col items-start gap-3 rounded-xl border border-[var(--border-default)] bg-[var(--surface-secondary)] px-4 py-5">
        <p className="flex items-center gap-2 text-sm font-semibold text-[var(--text-primary)]">
          <WarningCircle aria-hidden weight="duotone" className="size-5 text-[var(--text-muted)]" />
          {t("fitNoCvTitle")}
        </p>
        <p className="text-sm text-[var(--text-secondary)]">{t("fitNoCvBody")}</p>
        <Link href="/student/cv">
          <Button variant="primary" size="sm">{t("createCv")}</Button>
        </Link>
      </div>
    );
  }

  return (
    <div role="tabpanel" aria-labelledby="tab-fit" className="space-y-4">
      {/* Score-only headline: ring + which-CV + tier. */}
      <div className="flex items-start gap-4">
        <ScoreRing score={data.fit.score ?? 0} />
        <div className="min-w-0 flex-1 space-y-1.5">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-[var(--text-muted)]">
            {t("bestCvScoreLabel")}
          </p>
          <ReadinessChip readiness={readiness} />
          {readiness.stale && (
            <p className="flex items-start gap-1.5 text-[11px] leading-relaxed text-[var(--amber-700)]">
              <WarningCircle aria-hidden weight="duotone" className="mt-0.5 size-3.5 shrink-0" />
              {t("readiness.staleNote")}
            </p>
          )}
        </div>
      </div>

      {/* The 6 core HR evaluation criteria (deterministic, from the single fetch). */}
      {data.fit.bands && (
        <div className="grid grid-cols-2 gap-x-4 gap-y-2 text-xs">
          {BAND_ORDER.map((band, i) => (
            <BandMeter key={band} label={band} value={Math.round(data.fit.bands![band] ?? 0)} index={i} />
          ))}
        </div>
      )}

      {/* On-demand actions → drawers. Energy cost shown BEFORE running. */}
      <div className="space-y-2 border-t border-[var(--border-default)] pt-4">
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
          <DrawerButton icon={MagnifyingGlassPlus} label={t("analyzeCta")} onClick={onAnalyze} primary />
          <DrawerButton icon={Target} label={t("competitionCta")} onClick={onCompetition} />
        </div>
        <AiEnergyHint variant="inline" />
      </div>

      {/* WS-15: improve-then-apply entry routes through the Analyze drawer. */}
      {(readiness.level === "almost" || readiness.level === "needs_work") && (
        <button
          type="button"
          onClick={onAnalyze}
          className="flex w-full items-center justify-between gap-2 rounded-xl border border-[var(--border-default)] bg-[var(--surface-secondary)] px-3.5 py-2.5 text-left outline-none transition-colors hover:bg-[var(--surface-hover)] focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/30"
        >
          <span className="flex items-center gap-2 text-xs font-semibold text-[var(--text-primary)]">
            <Sparkle aria-hidden weight="duotone" className="size-4 text-[var(--brand-primary)]" />
            {t("improveThenApply")}
          </span>
          <ArrowUpRight aria-hidden weight="bold" className="size-3.5 shrink-0 text-[var(--text-muted)]" />
        </button>
      )}
    </div>
  );
}

function ReadinessChip({ readiness }: { readiness: CvReadiness }) {
  const t = useTranslations("jobs.studentIntel");
  const ready = readiness.level === "ready";
  const terminal = readiness.level === "applied" || readiness.level === "closed";
  const cls = ready
    ? "bg-[var(--teal-50)] text-[var(--teal-700)] border-[var(--teal-100)]"
    : terminal
      ? "bg-[var(--surface-secondary)] text-[var(--text-secondary)] border-[var(--border-default)]"
      : "bg-[var(--amber-50)] text-[var(--amber-700)] border-[var(--amber-100)]";
  return (
    <span className={cn("inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-semibold", cls)}>
      {ready && <CheckCircle aria-hidden weight="fill" className="size-3.5" />}
      {t(`readiness.${readiness.level}`)}
      {readiness.score !== null && (
        <span className="tabular-nums opacity-70">· {readiness.score}/100</span>
      )}
    </span>
  );
}

function DrawerButton({
  icon: Icon,
  label,
  onClick,
  primary,
}: {
  icon: React.ElementType;
  label: string;
  onClick: () => void;
  primary?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "flex items-center justify-center gap-1.5 rounded-xl border px-3 py-2.5 text-sm font-semibold outline-none transition-colors focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/30",
        primary
          ? "border-[var(--brand-primary)] bg-[var(--brand-primary)] text-[var(--text-inverted)] hover:opacity-90"
          : "border-[var(--border-default)] bg-[var(--surface-card)] text-[var(--text-primary)] hover:bg-[var(--surface-hover)]",
      )}
    >
      <Icon aria-hidden weight="duotone" className="size-4 shrink-0" />
      {label}
    </button>
  );
}

/**
 * The CV-JD fit score ring — the panel's signature element. A crisp, thin ring
 * with a big tabular score and a tier band label beneath it. Animates its arc +
 * number 0 → score on mount (respects `prefers-reduced-motion`).
 */
function ScoreRing({ score }: { score: number }) {
  const tf = useTranslations("cvFit");
  const reduced = usePrefersReducedMotion();
  const animated = useMountAnimation(reduced);

  const CIRC = 138.23; // 2πr, r = 22
  const target = Math.max(0, Math.min(100, score));
  const shownArc = animated ? target : 0;
  const dash = (shownArc / 100) * CIRC;
  const color = fitColor(target);
  const tier = fitTier(target);

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
      const eased = 1 - Math.pow(1 - p, 3);
      setDisplay(Math.round(eased * target));
      if (p < 1) raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [target, reduced]);

  return (
    <div className="flex w-[76px] shrink-0 flex-col items-center gap-1.5">
      <div
        className="relative size-[72px]"
        role="meter"
        aria-valuenow={target}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={tf("scoreAria", { score: target })}
      >
        <svg viewBox="0 0 56 56" className="size-[72px] -rotate-90" aria-hidden>
          <circle cx="28" cy="28" r="22" fill="none" stroke="var(--bg-muted)" strokeWidth="3.5" />
          <circle
            cx="28"
            cy="28"
            r="22"
            fill="none"
            stroke={color}
            strokeWidth="3.5"
            strokeLinecap="round"
            strokeDasharray={`${dash} ${CIRC}`}
            style={{
              transition: reduced ? "none" : "stroke-dasharray 800ms cubic-bezier(0.22,1,0.36,1)",
            }}
          />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center leading-none">
          <span className="text-2xl font-extrabold tabular-nums" style={{ color: fitTextColor(target) }}>
            {display}
          </span>
          <span className="mt-0.5 text-[9px] font-semibold text-[var(--text-muted)]">/100</span>
        </div>
      </div>
      {/* Band label — makes the ring self-describing (fit tier, not AI confidence). */}
      <span
        className="text-center text-[10px] font-bold uppercase leading-tight tracking-[0.06em]"
        style={{ color: fitTextColor(target) }}
      >
        {tf(`tier.${tier}`)}
      </span>
    </div>
  );
}

function BandMeter({ label, value, index }: { label: keyof StudentFitBands; value: number; index: number }) {
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
            transition: reduced ? "none" : "width 700ms cubic-bezier(0.22,1,0.36,1)",
            transitionDelay: reduced ? "0ms" : `${index * 45}ms`,
          }}
        />
      </div>
    </div>
  );
}

function ErrorBlock({ onRetry, disabled }: { onRetry: () => void; disabled: boolean }) {
  const t = useTranslations("jobs.studentIntel");
  return (
    <div role="alert" className="flex flex-col items-start gap-3 rounded-xl border border-[var(--border-default)] bg-[var(--surface-secondary)] px-4 py-4">
      <p className="flex items-center gap-2 text-sm font-semibold text-[var(--text-primary)]">
        <WarningCircle aria-hidden weight="duotone" className="size-5 text-[var(--brand-red)]" />
        {t("errorTitle")}
      </p>
      <p className="text-sm text-[var(--text-secondary)]">{t("errorBody")}</p>
      <Button variant="secondary" size="sm" onClick={onRetry} disabled={disabled}>
        <ArrowClockwise aria-hidden weight="bold" className="size-4" />
      </Button>
    </div>
  );
}

function FitSkeleton() {
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
        <Skeleton className="h-6 w-full" />
        <Skeleton className="h-6 w-full" />
      </div>
      <div className="grid grid-cols-2 gap-2">
        <Skeleton className="h-10 w-full rounded-xl" />
        <Skeleton className="h-10 w-full rounded-xl" />
      </div>
    </div>
  );
}
