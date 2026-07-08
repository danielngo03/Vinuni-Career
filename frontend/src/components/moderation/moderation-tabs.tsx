"use client";

import { useTranslations } from "next-intl";
import { useQuery } from "@tanstack/react-query";
import { Briefcase, CalendarBlank, ShieldWarning } from "@phosphor-icons/react";
import { Link, usePathname } from "@/i18n/navigation";
import { cn } from "@/lib/utils";
import { ApiError, aiReviewQueueApi } from "@/lib/api";

const TABS = [
  { key: "jobs", href: "/university/moderation/jobs", icon: Briefcase },
  { key: "events", href: "/university/moderation/events", icon: CalendarBlank },
  {
    key: "aiReview",
    href: "/university/moderation/ai-review",
    icon: ShieldWarning,
  },
] as const;

/**
 * Sub-navigation for the university moderation hub. The `/moderation` index and
 * `/moderation/jobs` both surface the jobs queue, so the Jobs tab is active for
 * either path. The "AI review" tab carries a live count badge of items awaiting
 * a human's final say over an AI/rule flag (B-579).
 */
export function ModerationTabs() {
  const t = useTranslations("moderationHub");
  const pathname = usePathname();

  // Lightweight badge count. Grant-gated on the backend; a 403/error simply
  // hides the badge (retry: false) rather than surfacing an error in the nav.
  const countsQuery = useQuery({
    queryKey: ["university", "ai-review-queue", "counts"],
    queryFn: () => aiReviewQueueApi.counts(),
    retry: false,
    staleTime: 30_000,
  });
  const aiCount =
    countsQuery.data && !(countsQuery.error instanceof ApiError)
      ? countsQuery.data.total
      : 0;

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
        const showBadge = tab.key === "aiReview" && aiCount > 0;
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
            {showBadge && (
              <span
                aria-label={t("aiReviewBadgeLabel", { count: aiCount })}
                className={cn(
                  "inline-flex min-w-5 items-center justify-center rounded-full px-1.5 text-xs font-bold tabular-nums",
                  active
                    ? "bg-white/25 text-white"
                    : "bg-[var(--amber-100)] text-[var(--amber-700)]",
                )}
              >
                {aiCount > 99 ? "99+" : aiCount}
              </span>
            )}
          </Link>
        );
      })}
    </div>
  );
}
