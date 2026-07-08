"use client";

import { useTranslations } from "next-intl";
import { Link } from "@/i18n/navigation";
import { BrandMark } from "./brand-mark";

const COL_PLATFORM_LINKS = [
  { key: "jobs" as const, href: "/jobs" },
  { key: "companies" as const, href: "/companies" },
  { key: "events" as const, href: "/events" },
  { key: "careerExplore" as const, href: "/careers" },
] as const;

const COL_STUDENT_LINKS = [
  { key: "studentDashboard" as const, href: "/student/dashboard" },
  { key: "cvStudio" as const, href: "/student/cv" },
  { key: "myApplications" as const, href: "/student/applications" },
  { key: "savedJobs" as const, href: "/student/saved" },
] as const;

const COL_EMPLOYER_LINKS = [
  { key: "employerDashboard" as const, href: "/partner/dashboard" },
  { key: "postJob" as const, href: "/partner/jobs/new" },
  { key: "candidates" as const, href: "/partner/candidates" },
] as const;

export function AppFooter() {
  const t = useTranslations("footer");
  const year = new Date().getFullYear();

  return (
    <footer className="border-t border-[var(--border-default)] bg-[var(--surface-card)]">
      <div className="mx-auto max-w-[1400px] px-4 py-10 lg:px-6">
        <div className="grid grid-cols-2 gap-8 sm:grid-cols-4">

          {/* Brand */}
          <div className="col-span-2 sm:col-span-1">
            <BrandMark className="scale-[0.92] origin-left" />
            <p className="mt-3 max-w-[230px] text-sm leading-relaxed text-[var(--text-secondary)]">
              {t("brandDescription")}
            </p>
          </div>

          {/* Platform */}
          <div>
            <p className="text-[11px] font-bold uppercase tracking-[0.12em] text-[var(--text-muted)]">
              {t("colPlatform")}
            </p>
            <ul className="mt-3 flex flex-col gap-2.5">
              {COL_PLATFORM_LINKS.map(({ key, href }) => (
                <li key={href}>
                  <Link href={href} className="text-sm font-medium text-[var(--text-secondary)] outline-none transition-colors hover:text-[var(--brand-primary)] focus-visible:underline">
                    {t(`links.${key}`)}
                  </Link>
                </li>
              ))}
            </ul>
          </div>

          {/* Students */}
          <div>
            <p className="text-[11px] font-bold uppercase tracking-[0.12em] text-[var(--text-muted)]">
              {t("colStudents")}
            </p>
            <ul className="mt-3 flex flex-col gap-2.5">
              {COL_STUDENT_LINKS.map(({ key, href }) => (
                <li key={href}>
                  <Link href={href} className="text-sm font-medium text-[var(--text-secondary)] outline-none transition-colors hover:text-[var(--brand-primary)] focus-visible:underline">
                    {t(`links.${key}`)}
                  </Link>
                </li>
              ))}
            </ul>
          </div>

          {/* Employers */}
          <div>
            <p className="text-[11px] font-bold uppercase tracking-[0.12em] text-[var(--text-muted)]">
              {t("colEmployers")}
            </p>
            <ul className="mt-3 flex flex-col gap-2.5">
              {COL_EMPLOYER_LINKS.map(({ key, href }) => (
                <li key={href}>
                  <Link href={href} className="text-sm font-medium text-[var(--text-secondary)] outline-none transition-colors hover:text-[var(--brand-primary)] focus-visible:underline">
                    {t(`links.${key}`)}
                  </Link>
                </li>
              ))}
            </ul>
          </div>

        </div>

        <div className="mt-10 flex flex-col items-start justify-between gap-2 border-t border-[var(--border-default)] pt-6 sm:flex-row sm:items-center">
          <p className="text-xs text-[var(--text-muted)]">
            {t("copyright", { year })}
          </p>
          <p className="text-xs text-[var(--text-muted)]">
            {t("address")}
          </p>
        </div>
      </div>
    </footer>
  );
}
