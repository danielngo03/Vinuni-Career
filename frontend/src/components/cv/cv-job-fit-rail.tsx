"use client";

import { useTranslations } from "next-intl";
import { useQuery } from "@tanstack/react-query";
import {
  ArrowClockwise,
  ArrowUpRight,
  Briefcase,
  CheckCircle,
  Target,
  WarningCircle,
  XCircle,
} from "@phosphor-icons/react";
import { Link } from "@/i18n/navigation";
import { Button, Skeleton } from "@/components/ui";
import { ApiError, cvApi } from "@/lib/api";
import { FIT_TIER_FILL, FIT_TIER_TEXT, fitTier } from "@/lib/cv/fit";

/**
 * Right-panel job-fit rail for the CV builder.
 *
 * When no `jobId` is supplied, shows an idle "check fit" prompt.
 * When `jobId` is set, fetches `GET /cvs/job-fit` and renders the
 * current CV's score, category bars, matched skills, and constructive
 * gaps. Filtering to the current `cvId` avoids showing a full CV-list
 * ranking in a single-CV context.
 *
 * Never labels the score as AI confidence and never shows provider/model
 * internals (docs/API_CONTRACTS.md §CV-To-Job Fit).
 */
export function CvJobFitRail({
  cvId,
  jobId,
}: {
  cvId: string;
  jobId?: string | null;
}) {
  const t = useTranslations("cvJobFitRail");
  const tc = useTranslations("common");

  const query = useQuery({
    queryKey: ["cv", "job-fit-rail", jobId],
    queryFn: () => cvApi.jobFit(jobId!),
    enabled: !!jobId,
    retry: false,
    staleTime: 60_000,
  });

  const result = query.data?.results.find((r) => r.cv_id === cvId) ?? null;
  const tier = result ? fitTier(result.score) : null;

  return (
    <div className="rounded-2xl border border-[var(--glass-border-strong)] bg-[var(--glass-surface)] p-5 shadow-[0_2px_16px_rgba(11,34,57,0.07)] backdrop-blur-md">
      {/* Header */}
      <div className="mb-4 flex items-start gap-2.5">
        <span className="flex size-9 shrink-0 items-center justify-center rounded-xl icon-chip-primary shadow-sm">
          <Target aria-hidden weight="duotone" className="size-5 text-white" />
        </span>
        <div className="min-w-0">
          <h2 className="text-base font-bold tracking-tight text-[var(--text-primary)]">
            {t("title")}
          </h2>
          {query.data?.job && (
            <p className="mt-0.5 truncate text-xs text-[var(--text-muted)]" title={query.data.job.title}>
              {query.data.job.title} · {query.data.job.company.display_name}
            </p>
          )}
          {!jobId && (
            <p className="mt-0.5 text-xs leading-relaxed text-[var(--text-muted)]">
              {t("idleSubtitle")}
            </p>
          )}
        </div>
      </div>

      {/* No job selected */}
      {!jobId && (
        <div className="space-y-3">
          <div className="rounded-xl border border-[var(--glass-border-strong)] bg-[var(--glass-surface-light)] px-4 py-4 backdrop-blur-sm">
            <p className="flex items-center gap-2 text-sm font-semibold text-[var(--text-primary)]">
              <Briefcase aria-hidden weight="duotone" className="size-5 text-[var(--text-muted)]" />
              {t("idleTitle")}
            </p>
            <p className="mt-1.5 text-xs leading-relaxed text-[var(--text-secondary)]">
              {t("idleBody")}
            </p>
          </div>
          <Link href="/jobs">
            <Button variant="secondary" size="sm" className="w-full">
              <ArrowUpRight aria-hidden weight="bold" className="size-4" />
              {t("browseJobs")}
            </Button>
          </Link>
          <Link href="/student/applications">
            <Button variant="ghost" size="sm" className="w-full">
              {t("viewApplications")}
            </Button>
          </Link>
        </div>
      )}

      {/* Loading */}
      {jobId && query.isPending && (
        <div className="space-y-3">
          <Skeleton className="h-14 w-full rounded-xl" />
          <Skeleton className="h-4 w-3/4 rounded" />
          <Skeleton className="h-4 w-1/2 rounded" />
        </div>
      )}

      {/* Error */}
      {jobId && query.isError && !(query.error instanceof ApiError && query.error.isNotFound) && (
        <div className="flex flex-col items-start gap-3 rounded-xl border border-[var(--glass-border-strong)] bg-[var(--glass-surface-light)] px-4 py-4 backdrop-blur-sm">
          <p className="flex items-center gap-2 text-sm font-semibold text-[var(--text-primary)]">
            <WarningCircle aria-hidden weight="duotone" className="size-5 text-[var(--brand-red)]" />
            {t("errorTitle")}
          </p>
          <Button variant="secondary" size="sm" onClick={() => query.refetch()} disabled={query.isFetching}>
            <ArrowClockwise aria-hidden weight="bold" className="size-4" />
            {tc("retry")}
          </Button>
        </div>
      )}

      {/* Fit result for this CV */}
      {jobId && result && tier && (
        <div className="space-y-4">
          {/* Score */}
          <div className="flex items-center gap-4">
            <div
              className="flex h-16 w-16 shrink-0 items-center justify-center rounded-full border-4"
              style={{ borderColor: FIT_TIER_FILL[tier] }}
              aria-label={t("scoreAria", { score: result.score })}
            >
              <span className="text-xl font-black" style={{ color: FIT_TIER_TEXT[tier] }}>
                {result.score}
              </span>
            </div>
            <div className="min-w-0">
              <p className="text-sm font-bold" style={{ color: FIT_TIER_TEXT[tier] }}>
                {t(`tier.${tier}`)}
              </p>
              <p className="mt-0.5 text-xs leading-relaxed text-[var(--text-secondary)]">
                {t(`tierHint.${tier}`)}
              </p>
            </div>
          </div>

          {/* Stale warning */}
          {result.stale && (
            <p className="flex items-start gap-2 rounded-xl bg-[var(--amber-50)] px-3.5 py-2.5 text-xs leading-relaxed text-[var(--amber-700)]">
              <WarningCircle aria-hidden weight="duotone" className="mt-0.5 size-4 shrink-0" />
              {t("staleNote")}
            </p>
          )}

          {/* Category bars */}
          <div className="space-y-2">
            {(["skills", "experience", "quality"] as const).map((band) => {
              const pct = Math.round(result.bands[band] ?? 0);
              return (
                <div key={band}>
                  <div className="mb-1 flex items-center justify-between">
                    <span className="text-xs font-medium text-[var(--text-secondary)]">
                      {t(`bands.${band}`)}
                    </span>
                    <span className="text-xs font-bold text-[var(--text-primary)]">{pct}</span>
                  </div>
                  <div className="h-1.5 overflow-hidden rounded-full bg-[var(--border-light)]">
                    <div
                      className="h-full rounded-full transition-all duration-500"
                      style={{ width: `${pct}%`, background: FIT_TIER_FILL[fitTier(pct)] }}
                    />
                  </div>
                </div>
              );
            })}
          </div>

          {/* Matched skills */}
          {result.matched_skills.length > 0 && (
            <div>
              <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-[var(--text-muted)]">
                {t("matchedTitle")}
              </p>
              <div className="flex flex-wrap gap-1.5">
                {result.matched_skills.slice(0, 8).map((s) => (
                  <span
                    key={s}
                    className="inline-flex items-center gap-1 rounded-full bg-[var(--teal-50)] px-2 py-0.5 text-xs font-medium text-[var(--teal-700)]"
                  >
                    <CheckCircle aria-hidden weight="fill" className="size-3" />
                    {s}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Gaps */}
          {result.gaps.length > 0 && (
            <div>
              <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-[var(--text-muted)]">
                {t("gapsTitle")}
              </p>
              <ul className="space-y-1">
                {result.gaps.slice(0, 5).map((g) => (
                  <li key={g} className="flex items-start gap-1.5 text-xs text-[var(--text-secondary)]">
                    <XCircle aria-hidden weight="duotone" className="mt-0.5 size-3.5 shrink-0 text-[var(--amber-500)]" />
                    {g}
                  </li>
                ))}
              </ul>
              <p className="mt-2 text-[10px] leading-relaxed text-[var(--text-muted)]">
                {t("gapsNote")}
              </p>
            </div>
          )}

          {/* Job link */}
          {query.data?.job && (
            <Link href={`/jobs/${query.data.job.id}`}>
              <Button variant="secondary" size="sm" className="w-full">
                <ArrowUpRight aria-hidden weight="bold" className="size-4" />
                {t("viewJob")}
              </Button>
            </Link>
          )}
        </div>
      )}

      {/* Job not found / CV not scored */}
      {jobId && !query.isPending && !query.isError && query.data && !result && (
        <div className="rounded-xl border border-[var(--glass-border-strong)] bg-[var(--glass-surface-light)] px-4 py-4 backdrop-blur-sm">
          <p className="text-sm text-[var(--text-secondary)]">{t("notScored")}</p>
        </div>
      )}
    </div>
  );
}
