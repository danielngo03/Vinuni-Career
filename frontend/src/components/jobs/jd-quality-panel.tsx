"use client";

import { useTranslations } from "next-intl";
import { CheckCircle, WarningCircle, Warning } from "@phosphor-icons/react";
import { cn } from "@/lib/utils";
import { Skeleton } from "@/components/ui";
import type { JobQualityIssue } from "@/lib/api";

/**
 * Field -> friendly label lookup used to route a quality-check finding to a
 * scannable group heading. Must stay in sync with the backend rubric
 * (`app.modules.opportunities.domain.jd_quality`); unknown fields fall back
 * to the raw field key so a new backend rule never renders blank.
 */
function fieldLabel(
  t: ReturnType<typeof useTranslations>,
  field: string,
): string {
  const known = [
    "title",
    "description",
    "requirements",
    "salary",
    "location_city",
    "experience",
    "screening_questions",
  ];
  return known.includes(field) ? t(`quality.fields.${field}`) : field;
}

function groupByField(issues: JobQualityIssue[]): Map<string, JobQualityIssue[]> {
  const out = new Map<string, JobQualityIssue[]>();
  for (const issue of issues) {
    const list = out.get(issue.field) ?? [];
    list.push(issue);
    out.set(issue.field, list);
  }
  return out;
}

/**
 * Scannable blocking-vs-advisory JD quality-check summary
 * (`GET /jobs/{job_id}/quality-check`). Renders a "all clear" state when
 * `passed && issues.length === 0`, otherwise groups findings by field with
 * blocking issues first.
 */
export function JdQualityPanel({
  issues,
  passed,
  loading,
  className,
  compact = false,
}: {
  issues: JobQualityIssue[];
  passed?: boolean;
  loading?: boolean;
  className?: string;
  compact?: boolean;
}) {
  const t = useTranslations("jobs");

  if (loading) {
    return (
      <div className={cn("space-y-2", className)}>
        <Skeleton className="h-5 w-1/2" />
        <Skeleton className="h-4 w-full" />
        <Skeleton className="h-4 w-2/3" />
      </div>
    );
  }

  const blocking = issues.filter((i) => i.severity === "blocking");
  const advisory = issues.filter((i) => i.severity === "advisory");

  if (issues.length === 0) {
    return (
      <div
        role="status"
        className={cn(
          "flex items-center gap-2 rounded-xl border border-[var(--teal-500)]/30 bg-[var(--teal-50)] px-3.5 py-2.5 text-sm font-medium text-[var(--teal-700)]",
          className,
        )}
      >
        <CheckCircle aria-hidden weight="fill" className="size-4.5 shrink-0" />
        {t("quality.allClear")}
      </div>
    );
  }

  return (
    <div className={cn("space-y-3", className)} aria-live="polite">
      {blocking.length > 0 && (
        <section
          role="alert"
          className="rounded-2xl border border-[var(--red-400)]/40 bg-[var(--red-50)] p-4"
        >
          <p className="mb-2 flex items-center gap-2 text-sm font-bold text-[var(--brand-red)]">
            <WarningCircle aria-hidden weight="fill" className="size-4.5 shrink-0" />
            {t("quality.blockingTitle", { count: blocking.length })}
          </p>
          <ul className="space-y-2">
            {Array.from(groupByField(blocking)).map(([field, list]) => (
              <li key={field}>
                {!compact && (
                  <p className="text-xs font-semibold uppercase tracking-wide text-[var(--brand-red)]/80">
                    {fieldLabel(t, field)}
                  </p>
                )}
                <ul className="space-y-1">
                  {list.map((issue, i) => (
                    <li
                      key={`${issue.field}-${issue.issue}-${i}`}
                      className="text-sm text-[var(--text-secondary)]"
                    >
                      {issue.message}
                    </li>
                  ))}
                </ul>
              </li>
            ))}
          </ul>
        </section>
      )}

      {advisory.length > 0 && (
        <section className="rounded-2xl border border-[var(--amber-600)]/40 bg-[var(--amber-100)] p-4">
          <p className="mb-2 flex items-center gap-2 text-sm font-bold text-[var(--amber-700)]">
            <Warning aria-hidden weight="fill" className="size-4.5 shrink-0" />
            {t("quality.advisoryTitle", { count: advisory.length })}
          </p>
          <ul className="space-y-2">
            {Array.from(groupByField(advisory)).map(([field, list]) => (
              <li key={field}>
                {!compact && (
                  <p className="text-xs font-semibold uppercase tracking-wide text-[var(--amber-700)]/80">
                    {fieldLabel(t, field)}
                  </p>
                )}
                <ul className="space-y-1">
                  {list.map((issue, i) => (
                    <li
                      key={`${issue.field}-${issue.issue}-${i}`}
                      className="text-sm text-[var(--text-secondary)]"
                    >
                      {issue.message}
                    </li>
                  ))}
                </ul>
              </li>
            ))}
          </ul>
        </section>
      )}
      {passed === false && blocking.length === 0 && (
        // Defensive: server said "not passed" but returned no blocking rows —
        // should not happen, but never silently claim all-clear.
        <p className="text-xs text-[var(--text-muted)]">{t("quality.recheckHint")}</p>
      )}
    </div>
  );
}

/** Inline, per-field note used inside `JobForm` — shows only that field's findings. */
export function JdFieldIssueNote({
  issues,
  field,
}: {
  issues: JobQualityIssue[] | undefined;
  field: string;
}) {
  const matches = (issues ?? []).filter((i) => i.field === field);
  if (matches.length === 0) return null;
  return (
    <ul className="mt-1.5 space-y-1">
      {matches.map((issue, i) => (
        <li
          key={`${field}-${i}`}
          className={cn(
            "flex items-start gap-1.5 text-xs font-medium",
            issue.severity === "blocking"
              ? "text-[var(--brand-red)]"
              : "text-[var(--amber-700)]",
          )}
        >
          {issue.severity === "blocking" ? (
            <WarningCircle aria-hidden weight="fill" className="mt-0.5 size-3.5 shrink-0" />
          ) : (
            <Warning aria-hidden weight="fill" className="mt-0.5 size-3.5 shrink-0" />
          )}
          {issue.message}
        </li>
      ))}
    </ul>
  );
}
