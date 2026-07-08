"use client";

import { useTranslations } from "next-intl";
import { Link, usePathname } from "@/i18n/navigation";
import {
  Buildings,
  CalendarCheck,
  ChartBar,
  FileMagnifyingGlass,
  FirstAidKit,
  UsersThree,
  WarningOctagon,
} from "@phosphor-icons/react";
import { PageHeader } from "@/components/layout/page-header";
import { cn } from "@/lib/utils";

const SECTIONS = [
  { key: "overview", href: "/university/career-services", icon: ChartBar },
  { key: "cohorts", href: "/university/career-services/cohorts", icon: UsersThree },
  { key: "atRisk", href: "/university/career-services/at-risk", icon: WarningOctagon },
  {
    key: "cvReview",
    href: "/university/career-services/cv-review",
    icon: FileMagnifyingGlass,
  },
  {
    key: "appointments",
    href: "/university/career-services/appointments",
    icon: CalendarCheck,
  },
  {
    key: "employerNotes",
    href: "/university/career-services/employer-notes",
    icon: Buildings,
  },
  {
    key: "interventions",
    href: "/university/career-services/interventions",
    icon: FirstAidKit,
  },
] as const;

/**
 * Shared shell for the counselor workspace (B-554): page header + a local
 * section sub-nav. Each section is its own route (independent RBAC/loading
 * state per `docs/API_CONTRACTS.md` resource), not tab-switched client state,
 * so a counselor without a given capability still gets a real URL + permission
 * state instead of a hidden tab.
 */
export function CareerServicesShell({
  title,
  description,
  actions,
  children,
}: {
  title: string;
  description?: string;
  actions?: React.ReactNode;
  children: React.ReactNode;
}) {
  const t = useTranslations("careerServices");
  const pathname = usePathname();

  return (
    <>
      <PageHeader title={title} description={description} actions={actions} />
      <nav
        aria-label={t("sectionsNavLabel")}
        className="mb-5 flex gap-2 overflow-x-auto pb-1"
      >
        {SECTIONS.map((section) => {
          const active = pathname === section.href;
          const Icon = section.icon;
          return (
            <Link
              key={section.key}
              href={section.href}
              aria-current={active ? "page" : undefined}
              className={cn(
                "inline-flex shrink-0 items-center gap-2 whitespace-nowrap rounded-full border px-4 py-2 text-sm font-semibold outline-none transition-all focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/30",
                active
                  ? "border-[var(--brand-primary)]/30 bg-[var(--brand-primary)] text-white shadow-sm shadow-[var(--brand-primary)]/20"
                  : "border-white/60 bg-white/72 text-[var(--text-secondary)] backdrop-blur-sm hover:bg-white/90 hover:text-[var(--text-primary)]",
              )}
            >
              <Icon aria-hidden weight="duotone" className="size-4" />
              {t(`sections.${section.key}`)}
            </Link>
          );
        })}
      </nav>
      {children}
    </>
  );
}
