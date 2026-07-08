"use client";

import { useTranslations } from "next-intl";
import { Briefcase, CalendarBlank } from "@phosphor-icons/react";
import { Link, usePathname } from "@/i18n/navigation";
import { cn } from "@/lib/utils";

const TABS = [
  { key: "jobs", href: "/university/moderation/jobs", icon: Briefcase },
  { key: "events", href: "/university/moderation/events", icon: CalendarBlank },
] as const;

/**
 * Sub-navigation for the university moderation hub. The `/moderation` index and
 * `/moderation/jobs` both surface the jobs queue, so the Jobs tab is active for
 * either path.
 */
export function ModerationTabs() {
  const t = useTranslations("moderationHub");
  const pathname = usePathname();

  function isActive(href: string) {
    if (href.endsWith("/jobs")) {
      return (
        pathname === "/university/moderation" ||
        pathname.startsWith("/university/moderation/jobs")
      );
    }
    return pathname.startsWith(href);
  }

  return (
    <div
      role="tablist"
      aria-label={t("tabsLabel")}
      className="mb-5 flex gap-2 overflow-x-auto"
    >
      {TABS.map((tab) => {
        const active = isActive(tab.href);
        const Icon = tab.icon;
        return (
          <Link
            key={tab.key}
            href={tab.href}
            role="tab"
            aria-selected={active}
            aria-current={active ? "page" : undefined}
            className={cn(
              "inline-flex items-center gap-2 whitespace-nowrap rounded-full border px-4 py-2 text-sm font-semibold outline-none transition-all focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/30 focus-visible:ring-offset-1",
              active
                ? "border-[var(--brand-primary)]/30 bg-[var(--brand-primary)] text-white shadow-sm shadow-[var(--brand-primary)]/20"
                : "border-[var(--border-default)] bg-white text-[var(--text-secondary)] hover:bg-white hover:text-[var(--text-primary)]",
            )}
          >
            <Icon aria-hidden weight="duotone" className="size-4" />
            {t(tab.key)}
          </Link>
        );
      })}
    </div>
  );
}
