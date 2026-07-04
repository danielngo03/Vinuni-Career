"use client";

import { useLocale, useTranslations } from "next-intl";
import {
  MapPin,
  Clock,
  Star,
  CaretRight,
} from "@phosphor-icons/react";
import { Link } from "@/i18n/navigation";
import { StatusBadge, SponsoredLabel } from "@/components/ui";
import { VerifiedBadge } from "@/components/ui/verified-badge";
import { CompanyAvatar } from "@/components/companies/company-avatar";
import { SaveJobButton } from "@/components/jobs/save-job-button";
import { useJobLabels } from "@/lib/jobs/labels";
import { formatLocation, formatJobLocationItem } from "@/lib/jobs/format";
import { formatRelativeTime } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { JobSummary } from "@/lib/api";

/**
 * Compact public job row for vertical lists (homepage recent jobs, company
 * "open roles"). Shows employer, role, work mode/location, deadline state, and
 * non-removable sponsored/featured labels. The whole row links to the detail
 * page; the guest apply flow lives on that page.
 */
export function JobRow({
  job,
  density = "default",
}: {
  job: JobSummary;
  density?: "default" | "compact";
}) {
  const t = useTranslations("jobs");
  const locale = useLocale();
  const labels = useJobLabels();
  const compact = density === "compact";

  const deadline = job.application_deadline
    ? new Date(job.application_deadline)
    : null;
  const isExpired = deadline ? deadline.getTime() < Date.now() : false;
  const postedLabel = formatRelativeTime(job.published_at, locale);

  return (
    <div
      className={cn(
        "group relative flex items-center gap-3 transition-colors hover:bg-[var(--surface-secondary)]",
        compact ? "px-3 py-2.5 sm:px-3.5 sm:py-3" : "p-3.5 sm:p-4",
      )}
    >
      <CompanyAvatar
        name={job.company?.display_name ?? job.title}
        logoUrl={job.company?.logo_url}
        size={compact ? "sm" : "md"}
        className={compact ? "flex" : "hidden sm:flex"}
      />

      <div className="min-w-0 flex-1">
        <div className={cn("flex flex-wrap items-center gap-1.5", compact ? "mb-0.5" : "mb-1")}>
          {job.is_sponsored && <SponsoredLabel label={t("sponsored")} />}
          {job.is_featured && (
            <StatusBadge tone="featured">
              <Star aria-hidden weight="fill" className="size-3" />
              {t("featured")}
            </StatusBadge>
          )}
        </div>

        <Link
          href={`/jobs/${job.id}`}
          className="after:absolute after:inset-0 rounded-md outline-none after:content-[''] focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/30"
        >
          <h3 className="truncate text-sm font-bold text-[var(--text-primary)] group-hover:text-[var(--brand-primary)]">
            {job.title}
          </h3>
        </Link>

        {job.company && (
          <p className="mt-0.5 flex items-center gap-1 text-xs font-medium text-[var(--text-secondary)]">
            <span className="truncate">{job.company.display_name}</span>
            {job.company.is_verified && (
              <VerifiedBadge label={t("verified")} className="[&_svg]:size-3.5" />
            )}
          </p>
        )}

        <div
          className={cn(
            "flex flex-wrap items-center text-xs text-[var(--text-muted)]",
            compact ? "mt-1 gap-x-2 gap-y-0.5" : "mt-1.5 gap-x-3 gap-y-1",
          )}
        >
          <span>
            {labels.employmentType(
              job.employment_type,
              job.employment_type_label,
            )}
            {" · "}
            {labels.locationType(job.location_type, job.location_type_label)}
          </span>
          <span className="flex items-center gap-1">
            <MapPin aria-hidden weight="duotone" className="size-3.5" />
            {job.locations && job.locations.length > 0
              ? job.locations.map(formatJobLocationItem).filter(Boolean).join(" · ")
              : formatLocation(job.location_city, job.location_country)}
          </span>
          {postedLabel && !deadline && (
            <span className="flex items-center gap-1">
              <Clock aria-hidden weight="duotone" className="size-3.5" />
              {postedLabel}
            </span>
          )}
          {deadline && (
            <span
              className={
                isExpired
                  ? "flex items-center gap-1 font-semibold text-[var(--brand-red)]"
                  : "flex items-center gap-1 font-medium text-[var(--amber-700)]"
              }
            >
              <Clock aria-hidden weight="duotone" className="size-3.5" />
              {isExpired
                ? t("expired")
                : `${t("deadline")}: ${deadline.toLocaleDateString(
                    locale === "vi" ? "vi-VN" : "en-US",
                  )}`}
            </span>
          )}
        </div>
      </div>

      <div className="relative z-10 flex shrink-0 items-center gap-2">
        <SaveJobButton jobId={job.id} size="sm" initialSaved={job.is_saved ?? false} />
        <CaretRight
          aria-hidden
          weight="bold"
          className="size-4 shrink-0 text-[var(--text-muted)] transition-colors group-hover:text-[var(--brand-primary)]"
        />
      </div>
    </div>
  );
}
