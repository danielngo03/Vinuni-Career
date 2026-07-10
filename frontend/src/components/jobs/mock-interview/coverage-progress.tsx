"use client";

import { useTranslations } from "next-intl";
import { CheckCircle, Circle, Target } from "@phosphor-icons/react";
import type { MockInterviewCoverage } from "@/lib/api";
import { cn } from "@/lib/utils";

/**
 * Leak-safe interview topic coverage (labels + counts only — never weights,
 * ids, tiers, or scores). Two surfaces share it:
 * - {@link CoverageChips}  — a subtle covered/remaining chip strip for the room.
 * - {@link CoverageReport} — a full "topics covered" section for the report.
 */

function safe(coverage: MockInterviewCoverage | null | undefined): MockInterviewCoverage | null {
  if (!coverage || typeof coverage.total !== "number" || coverage.total <= 0) return null;
  return {
    total: coverage.total,
    covered_count: Math.max(0, coverage.covered_count ?? 0),
    covered: Array.isArray(coverage.covered) ? coverage.covered.filter(Boolean) : [],
    remaining: Array.isArray(coverage.remaining) ? coverage.remaining.filter(Boolean) : [],
  };
}

/** Compact covered/remaining chip strip for the live room. */
export function CoverageChips({
  coverage,
  className,
}: {
  coverage: MockInterviewCoverage | null | undefined;
  className?: string;
}) {
  const t = useTranslations("jobs.mockInterview");
  const c = safe(coverage);
  if (!c) return null;

  const covered = c.covered;
  const remaining = c.remaining;
  const count = covered.length || c.covered_count;

  return (
    <div
      className={cn("flex flex-wrap items-center gap-1.5", className)}
      role="group"
      aria-label={t("coverageAria", { covered: count, total: c.total })}
    >
      <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-[var(--text-secondary)]">
        <Target aria-hidden weight="duotone" className="size-3.5 text-[var(--text-muted)]" />
        {t("coverageProgress", { covered: count, total: c.total })}
      </span>
      {covered.map((label, i) => (
        <span
          key={`c-${i}`}
          className="inline-flex items-center gap-1 rounded-full bg-[var(--teal-50)] px-2 py-0.5 text-[11px] font-medium text-[var(--teal-700)]"
        >
          <CheckCircle aria-hidden weight="fill" className="size-3" />
          {label}
        </span>
      ))}
      {remaining.map((label, i) => (
        <span
          key={`r-${i}`}
          className="inline-flex items-center gap-1 rounded-full border border-[var(--border-default)] bg-[var(--surface-card)] px-2 py-0.5 text-[11px] font-medium text-[var(--text-muted)]"
        >
          <Circle aria-hidden weight="regular" className="size-3" />
          {label}
        </span>
      ))}
    </div>
  );
}

/** Full topic-coverage section for the coaching report. */
export function CoverageReport({
  coverage,
}: {
  coverage: MockInterviewCoverage | null | undefined;
}) {
  const t = useTranslations("jobs.mockInterview");
  const c = safe(coverage);
  if (!c) return null;

  const coveredCount = c.covered.length || c.covered_count;
  const pct = Math.min(100, Math.round((coveredCount / c.total) * 100));

  return (
    <section className="rounded-2xl border border-[var(--border-default)] bg-[var(--surface-card)] p-5">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="flex items-center gap-2 text-sm font-bold text-[var(--text-primary)]">
            <Target aria-hidden weight="duotone" className="size-4 text-[var(--content-info)]" />
            {t("coverageReportTitle")}
          </h3>
          <p className="mt-0.5 text-xs text-[var(--text-secondary)]">
            {t("coverageReportSubtitle")}
          </p>
        </div>
        <span className="shrink-0 rounded-full bg-[var(--bg-subtle)] px-2.5 py-1 text-xs font-bold tabular-nums text-[var(--text-primary)]">
          {t("coverageProgress", { covered: coveredCount, total: c.total })}
        </span>
      </div>

      <div
        aria-hidden
        className="mt-3 h-2 w-full overflow-hidden rounded-full bg-[var(--bg-muted)]"
      >
        <div
          className="h-full rounded-full bg-[var(--content-info)] transition-[width] duration-500"
          style={{ width: `${Math.max(pct, coveredCount > 0 ? 4 : 0)}%` }}
        />
      </div>

      {c.covered.length > 0 && (
        <div className="mt-4">
          <p className="kicker mb-2">{t("coverageCoveredLabel")}</p>
          <div className="flex flex-wrap gap-1.5">
            {c.covered.map((label, i) => (
              <span
                key={i}
                className="inline-flex items-center gap-1 rounded-full bg-[var(--teal-50)] px-2.5 py-1 text-xs font-medium text-[var(--teal-700)]"
              >
                <CheckCircle aria-hidden weight="fill" className="size-3.5" />
                {label}
              </span>
            ))}
          </div>
        </div>
      )}

      {c.remaining.length > 0 && (
        <div className="mt-4">
          <p className="kicker mb-2">{t("coverageRemainingLabel")}</p>
          <div className="flex flex-wrap gap-1.5">
            {c.remaining.map((label, i) => (
              <span
                key={i}
                className="inline-flex items-center gap-1 rounded-full border border-[var(--border-default)] px-2.5 py-1 text-xs font-medium text-[var(--text-muted)]"
              >
                <Circle aria-hidden weight="regular" className="size-3.5" />
                {label}
              </span>
            ))}
          </div>
        </div>
      )}
    </section>
  );
}
