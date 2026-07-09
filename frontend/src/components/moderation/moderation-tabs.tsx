"use client";

import { useTranslations } from "next-intl";
import { Briefcase, CalendarDays } from "lucide-react";
import { Link, usePathname } from "@/i18n/navigation";
import { cn } from "@/lib/utils";

const TABS = [
  { key: "jobs", href: "/university/moderation/jobs", icon: Briefcase },
  { key: "events", href: "/university/moderation/events", icon: CalendarDays },
] as const;

/**
 * Sub-navigation for the university moderation hub. The `/moderation` index and
 * `/moderation/jobs` both surface the jobs queue, so the Jobs tab is active for
 * either path. v10 monochrome shell styling — ink pill for the active tab.
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
      className="mb-5 flex gap-1.5 overflow-x-auto"
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
              "inline-flex items-center gap-2 whitespace-nowrap rounded-full border px-4 py-1.5 text-[0.8125rem] font-semibold outline-none transition-colors focus-visible:ring-2 focus-visible:ring-[var(--field-focus-border)]",
              active
                ? "border-transparent bg-[var(--btn-primary-bg)] text-[var(--btn-primary-fg)]"
                : "border-border bg-card text-muted-foreground hover:border-border-strong hover:text-foreground",
            )}
          >
            <Icon aria-hidden className="size-4" strokeWidth={1.8} />
            {t(tab.key)}
          </Link>
        );
      })}
    </div>
  );
}
