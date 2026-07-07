"use client";

import { useMemo } from "react";
import { useTranslations } from "next-intl";
import { useQuery } from "@tanstack/react-query";
import {
  ArrowClockwise,
  ArrowUpRight,
  CheckCircle,
  FileText,
  LightbulbFilament,
  PlusCircle,
  Target,
  WarningCircle,
} from "@phosphor-icons/react";
import { Link } from "@/i18n/navigation";
import { Button, Skeleton } from "@/components/ui";
import { ApiError, cvApi, type JobFitResult } from "@/lib/api";
import {
  FIT_TIER_FILL,
  FIT_TIER_TEXT,
  fitTier,
  rankByScore,
} from "@/lib/cv/fit";
import { cn } from "@/lib/utils";

/**
 * CV-to-job fit panel for the authenticated **student** viewer. Renders the
 * recommended CV, its 0-100 product fit score, the four category meters,
 * matched skills, constructively-framed gaps, a stale warning, and an optional
 * explanation. Never labels the score/bands as "AI confidence" and never shows
 * provider/model/token internals (docs/API_CONTRACTS.md §CV-To-Job Fit).
 *
 * Render this only for authenticated students — the endpoint is owner-scoped.
 */
export function CvFitPanel({
  jobId,
  className,
}: {
  jobId: string;
  className?: string;
}) {
  const t = useTranslations("cvFit");
  const tc = useTranslations("common");

  const query = useQuery({
    queryKey: ["cv", "job-fit", jobId],
    queryFn: () => cvApi.jobFit(jobId),
    retry: false,
    staleTime: 60_000,
  });

  const ranked = useMemo(
    () => (query.data ? rankByScore(query.data.results) : []),
    [query.data],
  );

  // Job-fit 404 means the job isn't visible to score against — the surrounding
  // page already handles that; hide the panel rather than double-reporting.
  if (
    query.isError &&
    query.error instanceof ApiError &&
    query.error.isNotFound
  ) {
    return null;
  }

  const recommended =
    ranked.find((r) => r.cv_id === query.data?.recommended_cv_id) ?? ranked[0];
  const others = recommended
    ? ranked.filter((r) => r.cv_id !== recommended.cv_id)
    : ranked;

  return (
    <section
      aria-labelledby="cv-fit-title"
      className={cn(
        "rounded-2xl border border-white/60 bg-white/82 backdrop-blur-md p-5",
        className,
      )}
    >
      <header className="mb-4 flex items-start gap-2.5">
        <span className="flex size-9 shrink-0 items-center justify-center rounded-xl icon-chip-primary shadow-sm">
          <Target
            aria-hidden
            weight="duotone"
            className="size-5 text-white"
          />
        </span>
        <div className="min-w-0">
          <h2
            id="cv-fit-title"
            className="text-base font-bold tracking-tight text-[var(--text-primary)]"
          >
            {t("panelTitle")}
          </h2>
          <p className="mt-0.5 text-xs leading-relaxed text-[var(--text-muted)]">
            {t("panelSubtitle")}
          </p>
        </div>
      </header>

      {query.isPending ? (
        <FitSkeleton />
      ) : query.isError ? (
        <div
          role="alert"
          className="flex flex-col items-start gap-3 rounded-xl border border-white/60 bg-white/72 px-4 py-4 backdrop-blur-sm"
        >
          <p className="flex items-center gap-2 text-sm font-semibold text-[var(--text-primary)]">
            <WarningCircle
              aria-hidden
              weight="duotone"
              className="size-5 text-[var(--brand-red)]"
            />
            {t("errorTitle")}
          </p>
          <p className="text-sm text-[var(--text-secondary)]">{t("errorBody")}</p>
          <Button
            variant="secondary"
            size="sm"
            onClick={() => query.refetch()}
            disabled={query.isFetching}
          >
            <ArrowClockwise aria-hidden weight="bold" className="size-4" />
            {tc("retry")}
          </Button>
        </div>
      ) : !recommended ? (
        <div className="flex flex-col items-start gap-3 rounded-xl border border-white/60 bg-white/72 px-4 py-5 backdrop-blur-sm">
          <p className="flex items-center gap-2 text-sm font-semibold text-[var(--text-primary)]">
            <FileText
              aria-hidden
              weight="duotone"
              className="size-5 text-[var(--text-muted)]"
            />
            {t("emptyTitle")}
          </p>
          <p className="text-sm text-[var(--text-secondary)]">{t("emptyBody")}</p>
          <Link href="/student/cv">
            <Button variant="primary" size="sm">
              {t("createCv")}
            </Button>
          </Link>
        </div>
      ) : (
        <div className="space-y-5">
          {query.data?.signal === "low_signal" && (
            <p className="flex items-start gap-2 rounded-xl bg-[var(--amber-50)] px-3.5 py-2.5 text-xs leading-relaxed text-[var(--amber-700)]">
              <WarningCircle
                aria-hidden
                weight="duotone"
                className="mt-0.5 size-4 shrink-0"
              />
              {t("lowSignalNote")}
            </p>
          )}

          <RecommendedFit
            result={recommended}
            jobId={jobId}
            explanationAvailable={query.data?.ai_explanation_available ?? false}
          />

          {others.length > 0 && (
            <div className="border-t border-white/40 pt-4">
              <h3 className="mb-2.5 text-xs font-semibold uppercase tracking-wide text-[var(--text-muted)]">
                {t("otherTitle")}
              </h3>
              <ul className="space-y-1">
                {others.map((r) => (
                  <OtherCvRow key={r.cv_id} result={r} jobId={jobId} />
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </section>
  );
}

function RecommendedFit({
  result,
  jobId,
  explanationAvailable,
}: {
  result: JobFitResult;
  jobId: string;
  explanationAvailable: boolean;
}) {
  const t = useTranslations("cvFit");
  const tier = fitTier(result.score);
  const showExplanation = explanationAvailable && !!result.explanation;

  // Circle ring parameters: r=22, circumference = 2π×22 ≈ 138.23
  const CIRC = 138.23;
  const dash = (result.score / 100) * CIRC;

  return (
    <div className="space-y-4">
      {/* Score ring + recommended CV identity */}
      <div className="flex items-start gap-4">
        <div className="shrink-0 text-center">
          <div
            className="relative size-16"
            aria-label={t("scoreAria", { score: result.score })}
          >
            <svg
              viewBox="0 0 56 56"
              className="size-16 -rotate-90"
              aria-hidden
            >
              <circle
                cx="28"
                cy="28"
                r="22"
                fill="none"
                stroke="var(--bg-muted)"
                strokeWidth="5"
              />
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
              <span
                className="text-xl font-extrabold leading-none tabular-nums"
                style={{ color: FIT_TIER_TEXT[tier] }}
              >
                {result.score}
              </span>
              <span className="text-[9px] font-semibold text-[var(--text-muted)]">
                /100
              </span>
            </div>
          </div>
          <span
            className="mt-1.5 inline-block rounded-full px-2 py-0.5 text-[11px] font-semibold"
            style={{
              color: FIT_TIER_TEXT[tier],
              backgroundColor: "var(--bg-subtle)",
            }}
          >
            {t(`tier.${tier}` as "tier.strong")}
          </span>
        </div>
        <div className="min-w-0 flex-1">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-[var(--text-muted)]">
            {t("recommendedHeading")}
          </p>
          <p className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-sm font-bold text-[var(--text-primary)]">
            <span className="truncate">{result.title}</span>
            <span
              className="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-semibold text-white"
              style={{ backgroundColor: FIT_TIER_FILL[tier] }}
            >
              <CheckCircle aria-hidden weight="fill" className="size-3" />
              {t("recommendedTag")}
            </span>
          </p>
          <p className="mt-1 text-xs leading-relaxed text-[var(--text-secondary)]">
            {t(`tierHint.${tier}` as "tierHint.strong")}
          </p>
        </div>
      </div>

      {/* Category meters */}
      <div>
        <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-[var(--text-muted)]">
          {t("byCategory")}
        </h3>
        <div className="grid grid-cols-1 gap-x-5 gap-y-2.5 sm:grid-cols-2">
          <CategoryMeter label={t("bands.skills")} value={result.bands.skills} />
          <CategoryMeter
            label={t("bands.experience")}
            value={result.bands.experience}
          />
          <CategoryMeter label={t("bands.scope")} value={result.bands.scope} />
          <CategoryMeter
            label={t("bands.credentials")}
            value={result.bands.credentials}
          />
          <CategoryMeter
            label={t("bands.soft_skills")}
            value={result.bands.soft_skills}
          />
          <CategoryMeter
            label={t("bands.trajectory")}
            value={result.bands.trajectory}
          />
        </div>
      </div>

      {/* Matched skills */}
      <div>
        <h3 className="mb-1.5 flex items-center gap-1.5 text-xs font-semibold text-[var(--text-primary)]">
          <CheckCircle
            aria-hidden
            weight="duotone"
            className="size-4 text-[var(--teal-600)]"
          />
          {t("matchedTitle")}
        </h3>
        {result.matched_skills.length > 0 ? (
          <ul className="flex flex-wrap gap-1.5">
            {result.matched_skills.map((s) => (
              <li
                key={s}
                className="rounded-full bg-[var(--teal-50)] px-2.5 py-0.5 text-xs font-medium text-[var(--teal-600)]"
              >
                {s}
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-xs text-[var(--text-muted)]">{t("noMatched")}</p>
        )}
      </div>

      {/* Gaps — framed constructively, never as accusations */}
      <div>
        <h3 className="mb-1.5 flex items-center gap-1.5 text-xs font-semibold text-[var(--text-primary)]">
          <span className="flex size-5 shrink-0 items-center justify-center rounded-md icon-chip-warning shadow-sm">
            <PlusCircle aria-hidden weight="duotone" className="size-3 text-white" />
          </span>
          {t("gapsTitle")}
        </h3>
        {result.gaps.length > 0 ? (
          <>
            <ul className="flex flex-wrap gap-1.5">
              {result.gaps.map((g) => (
                <li
                  key={g}
                  className="rounded-full border border-dashed border-[var(--amber-600)]/40 bg-[var(--amber-50)] px-2.5 py-0.5 text-xs font-medium text-[var(--amber-700)]"
                >
                  {g}
                </li>
              ))}
            </ul>
            <p className="mt-1.5 text-[11px] leading-relaxed text-[var(--text-muted)]">
              {t("gapsNote")}
            </p>
          </>
        ) : (
          <p className="text-xs text-[var(--text-muted)]">{t("noGaps")}</p>
        )}
      </div>

      {/* Optional AI explanation — hidden entirely when unavailable */}
      {showExplanation && (
        <div className="flex items-start gap-2 rounded-xl border border-white/60 bg-white/72 px-3.5 py-3 backdrop-blur-sm">
          <LightbulbFilament
            aria-hidden
            weight="duotone"
            className="mt-0.5 size-4 shrink-0 text-[var(--ai-accent)]"
          />
          <div className="min-w-0">
            <p className="text-[11px] font-semibold uppercase tracking-wide text-[var(--text-muted)]">
              {t("whyTitle")}
            </p>
            <p className="mt-0.5 text-xs leading-relaxed text-[var(--text-secondary)]">
              {result.explanation}
            </p>
          </div>
        </div>
      )}

      {/* Stale warning + improve action */}
      {result.stale && (
        <p className="flex items-start gap-2 rounded-xl bg-[var(--amber-50)] px-3.5 py-2.5 text-xs leading-relaxed text-[var(--amber-700)]">
          <WarningCircle
            aria-hidden
            weight="duotone"
            className="mt-0.5 size-4 shrink-0"
          />
          <span>
            <span className="font-semibold">{t("staleTitle")}</span>{" "}
            {t("staleBody", { days: result.last_updated_days })}
          </span>
        </p>
      )}

      <Link href={`/student/cv/${result.cv_id}?job=${jobId}`}>
        <Button variant="secondary" size="sm" fullWidth>
          {t("improveCv")}
          <ArrowUpRight aria-hidden weight="bold" className="size-4" />
        </Button>
      </Link>
    </div>
  );
}

function CategoryMeter({ label, value }: { label: string; value: number }) {
  const tier = fitTier(value);
  return (
    <div>
      <div className="mb-1 flex items-center justify-between gap-2">
        <span className="text-xs font-medium text-[var(--text-secondary)]">
          {label}
        </span>
        <span className="text-xs font-semibold tabular-nums text-[var(--text-primary)]">
          {value}
        </span>
      </div>
      <div
        role="meter"
        aria-valuenow={value}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={label}
        className="h-2 w-full overflow-hidden rounded-full bg-[var(--bg-muted)]"
      >
        <div
          className="h-full rounded-full transition-[width] duration-500 motion-reduce:transition-none"
          style={{
            width: `${Math.max(2, value)}%`,
            backgroundColor: FIT_TIER_FILL[tier],
          }}
        />
      </div>
    </div>
  );
}

function OtherCvRow({ result, jobId }: { result: JobFitResult; jobId: string }) {
  const tier = fitTier(result.score);
  return (
    <li>
      <Link
        href={`/student/cv/${result.cv_id}?job=${jobId}`}
        className="flex items-center justify-between gap-3 rounded-lg px-2 py-1.5 outline-none transition-colors hover:bg-white/60 focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/30"
      >
        <span className="min-w-0 flex-1 truncate text-sm font-medium text-[var(--text-primary)]">
          {result.title}
        </span>
        <span
          className="shrink-0 text-sm font-bold tabular-nums"
          style={{ color: FIT_TIER_TEXT[tier] }}
        >
          {result.score}
          <span className="text-[11px] font-semibold text-[var(--text-muted)]">
            /100
          </span>
        </span>
      </Link>
    </li>
  );
}

function FitSkeleton() {
  return (
    <div className="space-y-4">
      <div className="flex items-start gap-4">
        <Skeleton className="size-16 rounded-xl" />
        <div className="flex-1 space-y-2">
          <Skeleton className="h-4 w-2/3" />
          <Skeleton className="h-3 w-1/2" />
        </div>
      </div>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <Skeleton className="h-6 w-full" />
        <Skeleton className="h-6 w-full" />
        <Skeleton className="h-6 w-full" />
        <Skeleton className="h-6 w-full" />
      </div>
      <Skeleton className="h-9 w-full" />
    </div>
  );
}
