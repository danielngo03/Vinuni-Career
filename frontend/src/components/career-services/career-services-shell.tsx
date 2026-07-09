"use client";

import { useTranslations } from "next-intl";
import { Link, usePathname } from "@/i18n/navigation";
import {
  LayoutDashboard,
  Users,
  AlertTriangle,
  FileSearch,
  CalendarCheck,
  Building2,
  HeartPulse,
} from "lucide-react";
import { PageHeader } from "@/components/layout/page-header";
import { cn } from "@/lib/utils";

const SECTIONS = [
  { key: "overview", href: "/university/career-services", icon: LayoutDashboard },
  { key: "cohorts", href: "/university/career-services/cohorts", icon: Users },
  { key: "atRisk", href: "/university/career-services/at-risk", icon: AlertTriangle },
  {
    key: "cvReview",
    href: "/university/career-services/cv-review",
    icon: FileSearch,
  },
  {
    key: "appointments",
    href: "/university/career-services/appointments",
    icon: CalendarCheck,
  },
  {
    key: "employerNotes",
    href: "/university/career-services/employer-notes",
    icon: Building2,
  },
  {
    key: "interventions",
    href: "/university/career-services/interventions",
    icon: HeartPulse,
  },
] as const;

/**
 * Shared shell for the counselor workspace (v10): page header + a local section
 * sub-nav. Each section is its own route (independent RBAC/loading state per
 * `docs/API_CONTRACTS.md` resource), not tab-switched client state, so a
 * counselor without a given capability still gets a real URL + permission state
 * instead of a hidden tab. Monochrome shell chips; content stays colourful.
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
        className="mb-5 flex gap-1.5 overflow-x-auto pb-1"
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
                "inline-flex shrink-0 items-center gap-2 whitespace-nowrap rounded-full border px-3.5 py-1.5 text-[0.8125rem] font-medium outline-none transition-colors focus-visible:ring-2 focus-visible:ring-[var(--field-focus-border)]",
                active
                  ? "border-transparent bg-foreground text-[var(--surface-card)]"
                  : "border-border bg-card text-muted-foreground hover:text-foreground",
              )}
            >
              <Icon aria-hidden className="size-4" strokeWidth={1.8} />
              {t(`sections.${section.key}`)}
            </Link>
          );
        })}
      </nav>
      {children}
    </>
  );
}
