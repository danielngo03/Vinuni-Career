"use client";

import { useLocale, useTranslations } from "next-intl";
import {
  MapPin,
  CurrencyCircleDollar,
  Clock,
  Star,
  Briefcase,
} from "@phosphor-icons/react";
import { Link } from "@/i18n/navigation";
import { StatusBadge, SponsoredLabel } from "@/components/ui";
import { VerifiedBadge } from "@/components/ui/verified-badge";
import { CompanyAvatar } from "@/components/companies/company-avatar";
import { SaveJobButton } from "@/components/jobs/save-job-button";
import { useJobLabels } from "@/lib/jobs/labels";
import { formatSalary, formatLocation, formatJobLocationItem } from "@/lib/jobs/format";
import { formatRelativeTime } from "@/lib/format";
import type { JobSummary } from "@/lib/api";

/**
 * Public job board card. Fixed-height structure for a stable grid.
 * Layout: company header row → title → compact meta → salary → skills.
 * A stretched overlay link makes the whole card navigate; the Heart save
 * button sits above it. Sponsored disclosure is non-removable.
 */
export function JobCard({ job }: { job: JobSummary }) {
  const t = useTranslations("jobs");
  const locale = useLocale();
  const labels = useJobLabels();
  const salary = formatSalary(job.salary, locale);
  const postedLabel = formatRelativeTime(job.published_at, locale);

  const locationText =
    job.locations && job.locations.length > 0
      ? job.locations.map(formatJobLocationItem).filter(Boolean).join(" · ")
      : formatLocation(job.location_city, job.location_country);

  const accentClass = job.is_sponsored
    ? "border-l-[3px] border-l-[var(--amber-500)]"
    : job.is_featured
      ? "border-l-[3px] border-l-[var(--brand-primary)]"
      : "";

  return (
    <div className={`marketplace-card marketplace-card-hover group relative flex h-full min-h-[206px] flex-col rounded-[14px] p-5 has-[a:focus-visible]:border-[var(--brand-primary)] has-[a:focus-visible]:ring-2 has-[a:focus-visible]:ring-[var(--brand-primary)]/30 ${accentClass}`}>
      {/* Stretched primary navigation — covers the whole card. */}
      <Link
        href={`/jobs/${job.id}`}
        aria-label={job.title}
        className="absolute inset-0 z-0 rounded-[14px] outline-none"
      />

      {/* Save button — above the link so it's clickable independently. */}
      <div className="absolute right-3 top-3 z-10">
        <SaveJobButton jobId={job.id} size="sm" initialSaved={job.is_saved ?? false} />
      </div>

      {/* Content */}
      <div className="pointer-events-none relative z-[1] flex h-full flex-col">

        {/* Company header row */}
        <div className="mb-3 flex items-start gap-2.5">
          {job.company ? (
            <CompanyAvatar
              name={job.company.display_name}
              logoUrl={job.company.logo_url}
              size="md"
            />
          ) : (
            <span
              aria-hidden
              className="flex size-10 shrink-0 items-center justify-center rounded-xl icon-chip-primary shadow-sm"
            >
              <Briefcase weight="duotone" className="size-5 text-white" />
            </span>
          )}
          <div className="min-w-0 flex-1 pr-8">
            {job.company && (
              <p className="flex items-center gap-1 text-xs font-semibold text-[var(--text-secondary)]">
                <span className="truncate">{job.company.display_name}</span>
                {job.company.is_verified && (
                  <VerifiedBadge label={t("verified")} className="[&_svg]:size-3.5" />
                )}
              </p>
            )}
            {postedLabel && (
              <p className="flex items-center gap-1 text-[0.7rem] text-[var(--text-muted)]">
                <Clock aria-hidden weight="duotone" className="size-3 shrink-0" />
                {postedLabel}
              </p>
            )}
          </div>
        </div>

        {/* Disclosure badges */}
        {(job.is_sponsored || job.is_featured) && (
          <div className="mb-2 flex flex-wrap gap-1">
            {job.is_sponsored && <SponsoredLabel label={t("sponsored")} />}
            {job.is_featured && (
              <StatusBadge tone="featured">
                <Star aria-hidden weight="fill" className="size-3" />
                {t("featured")}
              </StatusBadge>
            )}
          </div>
        )}

        {/* Job title */}
        <h3 className="line-clamp-2 text-base font-bold tracking-tight text-[var(--text-primary)] group-hover:text-[var(--brand-primary)]">
          {job.title}
        </h3>

        {/* Compact meta row */}
        <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-[var(--text-secondary)]">
          <span>
            {labels.employmentType(job.employment_type, job.employment_type_label)}
            {" · "}
            {labels.locationType(job.location_type, job.location_type_label)}
          </span>
          {locationText && (
            <span className="flex items-center gap-1 text-[var(--text-muted)]">
              <MapPin aria-hidden weight="duotone" className="size-3.5 shrink-0" />
              <span className="truncate max-w-[120px]">{locationText}</span>
            </span>
          )}
        </div>

        {/* Salary — monospace numeric pill when disclosed */}
        {salary ? (
          <p className="mt-2.5 flex items-center gap-1.5 rounded-lg border border-[var(--border-default)] bg-[var(--bg-muted)] px-2.5 py-1.5 text-xs text-[var(--text-secondary)]">
            <CurrencyCircleDollar aria-hidden weight="duotone" className="size-3.5 shrink-0" />
            <span className="font-data font-semibold tabular-nums">{salary}</span>
          </p>
        ) : (
          <p className="mt-2.5 text-xs text-[var(--text-muted)]">{t("salaryUndisclosed")}</p>
        )}

        {/* Skills */}
        {job.required_skills.length > 0 && (
          <ul className="mt-3 flex flex-1 flex-wrap items-end gap-1.5">
            {job.required_skills.slice(0, 4).map((skill) => (
              <li
                key={skill}
                className="rounded-full border border-[var(--border-default)] bg-[var(--surface-secondary)] px-2.5 py-0.5 text-xs font-medium text-[var(--text-secondary)]"
              >
                {skill}
              </li>
            ))}
            {job.required_skills.length > 4 && (
              <li className="px-1 py-0.5 text-xs font-medium text-[var(--text-muted)]">
                +{job.required_skills.length - 4}
              </li>
            )}
          </ul>
        )}

        {/* Deadline footer */}
        {job.application_deadline && (
          <p className="mt-2.5 self-end text-xs font-semibold text-[var(--amber-700)]">
            {t("deadline")}: {new Date(job.application_deadline).toLocaleDateString(
              locale === "vi" ? "vi-VN" : "en-US",
            )}
          </p>
        )}
      </div>
    </div>
  );
}
