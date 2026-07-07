"use client";

import { useEffect, useRef, useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import {
  Briefcase,
  Buildings,
  CalendarBlank,
  Clock,
  CurrencyCircleDollar,
  Flag,
  MapPin,
  Sparkle,
  Star,
  UsersThree,
  X,
  type Icon,
} from "@phosphor-icons/react";
import { Link } from "@/i18n/navigation";
import { CompanyAvatar } from "@/components/companies/company-avatar";
import { SaveJobButton } from "@/components/jobs/save-job-button";
import { Skeleton, SponsoredLabel, StatusBadge } from "@/components/ui";
import { VerifiedBadge } from "@/components/ui/verified-badge";
import type { JobSummary, PublicJobDetail } from "@/lib/api";
import { formatRelativeTime } from "@/lib/format";
import {
  formatJobLocationItem,
  formatLocation,
  jobSalaryLabel,
} from "@/lib/jobs/format";
import { useJobLabels } from "@/lib/jobs/labels";
import { cn } from "@/lib/utils";

const DESCRIPTION_CLAMP = 320;

function compactJobLocation(job: JobSummary) {
  const locations =
    job.locations && job.locations.length > 0
      ? job.locations.map(formatJobLocationItem).filter(Boolean)
      : [formatLocation(job.location_city, job.location_country)];
  if (locations.length <= 1) return locations[0] || "—";
  return `${locations[0]} +${locations.length - 1}`;
}

/**
 * Right-docked job detail drawer opened from the marketplace board (replaces the
 * old inline preview panel). Reuses the already-wired `detailQuery` result. It
 * is an honest surface: no fabricated AI summary or applicant PII — only public
 * projection fields. Students see their CV-JD fit badge; guests never do.
 *
 * A11y: `role="dialog"` + `aria-modal`; Escape and backdrop click close; the
 * close button receives focus on open; body scroll locks while open.
 */
export function JobDetailModal({
  open,
  summary,
  detail,
  loading,
  onClose,
  fitScore,
  isStudent,
}: {
  open: boolean;
  summary: JobSummary | null;
  detail: PublicJobDetail | undefined;
  loading: boolean;
  onClose: () => void;
  fitScore?: number | null;
  isStudent: boolean;
}) {
  const t = useTranslations("jobs");
  const locale = useLocale();
  const labels = useJobLabels();
  const [descExpanded, setDescExpanded] = useState(false);
  const [shown, setShown] = useState(false);
  const closeRef = useRef<HTMLButtonElement>(null);

  // Drive the enter transition: first paint renders off-screen, then a rAF
  // flips `shown` so the panel slides in / the backdrop fades in.
  useEffect(() => {
    if (!open) {
      setShown(false);
      return;
    }
    const id = requestAnimationFrame(() => setShown(true));
    return () => cancelAnimationFrame(id);
  }, [open]);

  // Lock body scroll + wire Escape while open; focus the close button.
  useEffect(() => {
    if (!open) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    closeRef.current?.focus();
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("keydown", onKey);
    return () => {
      document.body.style.overflow = prev;
      document.removeEventListener("keydown", onKey);
    };
  }, [open, onClose]);

  // Reset the description clamp whenever a new job is opened.
  useEffect(() => {
    setDescExpanded(false);
  }, [summary?.id]);

  if (!open || !summary) return null;

  const job = detail ?? summary;
  const salary = jobSalaryLabel(job, locale) ?? t("salaryUndisclosed");
  const posted = formatRelativeTime(job.published_at, locale);
  const rating = job.company?.rating;
  const deadline = job.application_deadline
    ? new Intl.DateTimeFormat(locale === "vi" ? "vi-VN" : "en-US", {
        dateStyle: "medium",
      }).format(new Date(job.application_deadline))
    : t("noDeadline");
  const description = detail?.description ?? "";
  const requirements = detail?.requirements ?? "";
  const skills =
    job.required_skills.length > 0
      ? job.required_skills
      : detail?.preferred_skills ?? [];
  const showFit = isStudent && typeof fitScore === "number";
  const longDescription = description.length > DESCRIPTION_CLAMP;
  const shownDescription =
    longDescription && !descExpanded
      ? `${description.slice(0, DESCRIPTION_CLAMP).trimEnd()}…`
      : description;

  return (
    <div className="fixed inset-0 z-[60]" role="dialog" aria-modal="true" aria-label={t("detailTitle")}>
      {/* Backdrop */}
      <button
        type="button"
        aria-label={t("closePreview")}
        onClick={onClose}
        className={cn(
          "absolute inset-0 h-full w-full cursor-default bg-black/40 backdrop-blur-[2px] transition-opacity duration-300",
          shown ? "opacity-100" : "opacity-0",
        )}
      />

      {/* Panel */}
      <div
        className={cn(
          "absolute inset-y-0 right-0 flex w-full max-w-[560px] flex-col bg-[var(--surface-card)] shadow-[0_0_60px_rgba(0,0,0,0.28)] transition-transform duration-300 ease-out",
          shown ? "translate-x-0" : "translate-x-full",
        )}
      >
        {/* Top bar */}
        <div className="flex shrink-0 items-center justify-between gap-3 border-b border-[var(--border-default)] px-5 py-3.5">
          <p className="text-sm font-bold text-[var(--text-primary)]">
            {t("detailTitle")}
          </p>
          <div className="flex items-center gap-1">
            <Link
              href={`/jobs/${job.id}?report=1`}
              className="inline-flex items-center gap-1.5 rounded-full px-2.5 py-1.5 text-xs font-semibold text-[var(--brand-red)] outline-none transition-colors hover:bg-[var(--brand-red)]/10 focus-visible:ring-2 focus-visible:ring-[var(--brand-red)]/30"
            >
              <Flag aria-hidden weight="duotone" className="size-4" />
              <span className="hidden sm:inline">{t("reportJob")}</span>
            </Link>
            <button
              ref={closeRef}
              type="button"
              aria-label={t("closePreview")}
              onClick={onClose}
              className="flex size-9 items-center justify-center rounded-full text-[var(--text-muted)] outline-none transition-colors hover:bg-[var(--surface-secondary)] hover:text-[var(--text-primary)] focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/30"
            >
              <X aria-hidden weight="bold" className="size-4" />
            </button>
          </div>
        </div>

        {/* Scroll body */}
        <div className="min-h-0 flex-1 overflow-y-auto px-5 py-5">
          {/* Title + disclosure + fit */}
          <div className="flex flex-wrap items-center gap-1.5">
            {job.is_sponsored && <SponsoredLabel label={t("sponsored")} />}
            {job.is_featured && (
              <StatusBadge tone="featured">
                <Star aria-hidden weight="fill" className="size-3" />
                {t("featured")}
              </StatusBadge>
            )}
            {showFit && (
              <span className="inline-flex items-center gap-1 rounded-full border border-[var(--text-primary)] bg-[var(--text-primary)] px-2.5 py-1 text-xs font-bold text-[var(--surface-card)]">
                <Sparkle aria-hidden weight="fill" className="size-3.5" />
                {t("fitScoreShort", { score: fitScore })}
              </span>
            )}
          </div>

          <h2 className="mt-2.5 text-2xl font-extrabold leading-tight tracking-tight text-[var(--text-primary)]">
            {job.title}
          </h2>

          {job.company && (
            <Link
              href={`/companies/${job.company.slug}`}
              className="group mt-3 flex w-fit items-center gap-2.5 rounded-lg outline-none focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/30"
            >
              <CompanyAvatar
                name={job.company.display_name}
                logoUrl={job.company.logo_url}
                size="sm"
              />
              <span className="flex min-w-0 items-center gap-1.5 text-sm font-semibold text-[var(--text-secondary)]">
                <span className="truncate group-hover:text-[var(--brand-primary)] group-hover:underline">
                  {job.company.display_name}
                </span>
                {job.company.is_verified && (
                  <VerifiedBadge label={t("verified")} className="[&_svg]:size-3.5" />
                )}
                {rating?.overall_avg != null && (
                  <span className="inline-flex items-center gap-1 rounded-full bg-[var(--surface-secondary)] px-2 py-0.5 text-xs font-semibold text-[var(--text-secondary)]">
                    <Star aria-hidden weight="fill" className="size-3.5 text-amber-500" />
                    {rating.overall_avg.toFixed(1)}
                  </span>
                )}
              </span>
            </Link>
          )}

          {/* Meta row */}
          <div className="mt-4 flex flex-wrap items-center gap-x-3 gap-y-1.5 text-xs font-medium text-[var(--text-muted)]">
            <span className="inline-flex items-center gap-1">
              <Briefcase aria-hidden weight="duotone" className="size-3.5" />
              {labels.employmentType(job.employment_type, job.employment_type_label)}
              {" · "}
              {labels.locationType(job.location_type, job.location_type_label)}
            </span>
            <span className="inline-flex items-center gap-1">
              <MapPin aria-hidden weight="duotone" className="size-3.5" />
              {compactJobLocation(job)}
            </span>
            {posted && (
              <span className="inline-flex items-center gap-1">
                <Clock aria-hidden weight="duotone" className="size-3.5" />
                {posted}
              </span>
            )}
          </div>

          {/* Stat cards */}
          <div className="mt-5 grid grid-cols-3 gap-2.5">
            <StatCard icon={CurrencyCircleDollar} label={t("salary")} value={salary} />
            <StatCard icon={CalendarBlank} label={t("deadline")} value={deadline} />
            {detail ? (
              <StatCard
                icon={UsersThree}
                label={t("headcount")}
                value={String(detail.headcount)}
              />
            ) : (
              <div className="rounded-xl border border-[var(--border-default)] bg-[var(--surface-secondary)] p-3">
                <Skeleton className="h-3.5 w-14" />
                <Skeleton className="mt-2 h-4 w-10" />
              </div>
            )}
          </div>

          {/* Description */}
          <Section title={t("description")}>
            {loading && !detail ? (
              <div className="space-y-2">
                <Skeleton className="h-4 w-full" />
                <Skeleton className="h-4 w-11/12" />
                <Skeleton className="h-4 w-9/12" />
              </div>
            ) : description ? (
              <>
                <p className="whitespace-pre-line text-sm leading-7 text-[var(--text-secondary)]">
                  {shownDescription}
                </p>
                {longDescription && (
                  <button
                    type="button"
                    onClick={() => setDescExpanded((v) => !v)}
                    className="mt-1.5 text-sm font-semibold text-[var(--text-primary)] underline-offset-4 outline-none transition-colors hover:underline focus-visible:underline"
                  >
                    {descExpanded ? t("seeLess") : t("seeMore")}
                  </button>
                )}
              </>
            ) : (
              <p className="text-sm text-[var(--text-muted)]">{t("noRequirements")}</p>
            )}
          </Section>

          {/* Requirements */}
          {requirements && (
            <Section title={t("requirements")}>
              <p className="whitespace-pre-line text-sm leading-7 text-[var(--text-secondary)]">
                {requirements}
              </p>
            </Section>
          )}

          {/* Benefits */}
          {detail?.benefits && (
            <Section title={t("benefits")}>
              <p className="whitespace-pre-line text-sm leading-7 text-[var(--text-secondary)]">
                {detail.benefits}
              </p>
            </Section>
          )}

          {/* Skills */}
          {skills.length > 0 && (
            <Section title={t("skillsTitle")}>
              <div className="flex flex-wrap gap-2">
                {skills.slice(0, 12).map((skill) => (
                  <span
                    key={skill}
                    className="rounded-full border border-[var(--border-default)] bg-[var(--surface-secondary)] px-3 py-1 text-xs font-semibold text-[var(--text-secondary)]"
                  >
                    {skill}
                  </span>
                ))}
              </div>
            </Section>
          )}
        </div>

        {/* Sticky footer */}
        <div className="flex shrink-0 items-center gap-2 border-t border-[var(--border-default)] px-5 py-3.5">
          <SaveJobButton jobId={job.id} size="md" initialSaved={job.is_saved ?? false} />
          <Link
            href={`/jobs/${job.id}`}
            className="inline-flex h-10 flex-1 items-center justify-center rounded-full border border-[var(--border-strong)] bg-[var(--surface-card)] px-4 text-sm font-semibold text-[var(--text-primary)] outline-none transition-colors hover:bg-[var(--bg-subtle)] focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/30"
          >
            <Buildings aria-hidden weight="duotone" className="mr-1.5 size-4" />
            {t("viewFullDetail")}
          </Link>
          <Link
            href={`/jobs/${job.id}`}
            className="inline-flex h-10 flex-1 items-center justify-center rounded-full bg-[var(--btn-primary-bg)] px-4 text-sm font-semibold text-[var(--btn-primary-fg)] shadow-[var(--shadow-brand)] outline-none transition-colors hover:bg-[var(--btn-primary-hover)] focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/30"
          >
            {t("apply")}
          </Link>
        </div>
      </div>
    </div>
  );
}

function StatCard({
  icon: IconCmp,
  label,
  value,
}: {
  icon: Icon;
  label: string;
  value: string;
}) {
  return (
    <div className="rounded-xl border border-[var(--border-default)] bg-[var(--surface-secondary)] p-3">
      <p className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-[0.04em] text-[var(--text-muted)]">
        <IconCmp aria-hidden weight="duotone" className="size-3.5" />
        <span className="truncate">{label}</span>
      </p>
      <p className="mt-1.5 truncate text-sm font-bold text-[var(--text-primary)]">
        {value}
      </p>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="mt-6">
      <h3 className="mb-2.5 text-sm font-bold text-[var(--text-primary)]">{title}</h3>
      {children}
    </div>
  );
}
