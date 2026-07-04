"use client";

import { useLocale, useTranslations } from "next-intl";
import {
  Briefcase,
  MapPin,
  CurrencyCircleDollar,
  Clock,
  Users,
  GraduationCap,
  SealCheck,
  Star,
} from "@phosphor-icons/react";
import { StatusBadge, SponsoredLabel } from "@/components/ui";
import { CompanyAvatar } from "@/components/companies/company-avatar";
import { useJobLabels } from "@/lib/jobs/labels";
import { formatSalary, formatLocation } from "@/lib/jobs/format";
import type { PublicJobDetail } from "@/lib/api";

/**
 * Read-only mirror of the public job detail presentation
 * (`components/jobs/public-job-detail.tsx`), used only inside the partner
 * "preview as guest/student" surface. Deliberately has no apply CTA, save
 * button, or personalization — this is a preview, not the live page.
 */
export function JobPreviewContent({ job }: { job: PublicJobDetail }) {
  const t = useTranslations("jobs");
  const locale = useLocale();
  const labels = useJobLabels();
  const salary = formatSalary(job.salary, locale);

  return (
    <div className="min-w-0 overflow-hidden rounded-[16px] border border-[var(--border-default)] bg-white">
      <header className="border-b border-[var(--border-default)] bg-[var(--surface-card)] p-4 sm:p-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          {job.company && (
            <span className="inline-flex items-center gap-2.5 rounded-full border border-[var(--border-default)] bg-[var(--surface-secondary)] px-3 py-1.5 text-sm font-semibold text-[var(--text-primary)]">
              <CompanyAvatar
                name={job.company.display_name}
                logoUrl={job.company.logo_url}
                size="sm"
              />
              <span>{job.company.display_name}</span>
              {job.company.is_verified && (
                <SealCheck
                  aria-label={t("verifiedPartner")}
                  weight="fill"
                  className="size-4 text-[var(--brand-teal)]"
                />
              )}
            </span>
          )}
          <div className="flex items-center gap-2">
            {job.is_sponsored && <SponsoredLabel label={t("sponsored")} />}
            {job.is_featured && (
              <StatusBadge tone="featured">
                <Star aria-hidden weight="fill" className="size-3" />
                {t("featured")}
              </StatusBadge>
            )}
          </div>
        </div>

        <h1 className="mt-4 text-xl font-extrabold leading-tight tracking-tight text-[var(--text-primary)] sm:text-2xl">
          {job.title}
        </h1>

        <dl className="mt-4 grid grid-cols-1 gap-2 sm:grid-cols-2">
          <PreviewMeta icon={Briefcase} label={t("employmentType")}>
            {labels.employmentType(job.employment_type, job.employment_type_label)}
            {" · "}
            {labels.locationType(job.location_type, job.location_type_label)}
          </PreviewMeta>
          <PreviewMeta icon={MapPin} label={t("location")}>
            {formatLocation(job.location_city, job.location_country)}
          </PreviewMeta>
          <PreviewMeta icon={CurrencyCircleDollar} label={t("salary")}>
            {salary ?? t("salaryUndisclosed")}
          </PreviewMeta>
          <PreviewMeta icon={Users} label={t("headcount")}>
            {job.headcount}
          </PreviewMeta>
          {job.experience_display && (
            <PreviewMeta icon={Clock} label={t("experience")}>
              {job.experience_display.label}
            </PreviewMeta>
          )}
          {job.degree_required && (
            <PreviewMeta icon={GraduationCap} label={t("degree")}>
              {job.degree_required}
            </PreviewMeta>
          )}
        </dl>
      </header>

      <div className="p-4 sm:p-5">
        <PreviewSection title={t("description")}>{job.description}</PreviewSection>
        {job.requirements && (
          <PreviewSection title={t("requirements")}>{job.requirements}</PreviewSection>
        )}
        {job.benefits && (
          <PreviewSection title={t("benefits")}>{job.benefits}</PreviewSection>
        )}
        {job.required_skills.length > 0 && (
          <PreviewSkills title={t("requiredSkills")} skills={job.required_skills} />
        )}
        {job.preferred_skills.length > 0 && (
          <PreviewSkills title={t("preferredSkills")} skills={job.preferred_skills} />
        )}
      </div>
    </div>
  );
}

function PreviewMeta({
  icon: Icon,
  label,
  children,
}: {
  icon: React.ElementType;
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex items-start gap-2 rounded-lg bg-[var(--surface-secondary)] px-3 py-2">
      <Icon aria-hidden weight="duotone" className="mt-0.5 size-4 shrink-0 text-[var(--brand-primary)]" />
      <div className="min-w-0">
        <dt className="text-xs font-medium text-[var(--text-muted)]">{label}</dt>
        <dd className="text-sm font-semibold text-[var(--text-primary)]">{children}</dd>
      </div>
    </div>
  );
}

function PreviewSection({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="mt-5 border-t border-[var(--border-default)]/70 pt-4 first:mt-0 first:border-t-0 first:pt-0">
      <h2 className="mb-2 text-sm font-bold tracking-tight text-[var(--text-primary)]">{title}</h2>
      <p className="whitespace-pre-wrap text-sm leading-6 text-[var(--text-secondary)]">
        {children}
      </p>
    </section>
  );
}

function PreviewSkills({ title, skills }: { title: string; skills: string[] }) {
  return (
    <section className="mt-4">
      <h2 className="mb-2 text-xs font-semibold text-[var(--text-primary)]">{title}</h2>
      <ul className="flex flex-wrap gap-1.5">
        {skills.map((s) => (
          <li
            key={s}
            className="rounded-full border border-[var(--border-default)] bg-[var(--surface-secondary)] px-2.5 py-1 text-xs font-medium text-[var(--text-secondary)]"
          >
            {s}
          </li>
        ))}
      </ul>
    </section>
  );
}
