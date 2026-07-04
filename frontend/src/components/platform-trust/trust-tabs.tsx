"use client";

import { useTranslations } from "next-intl";
import { LifeBuoy, Lock, ShieldAlert } from "lucide-react";
import { Link, usePathname } from "@/i18n/navigation";
import { cn } from "@/lib/utils";

const TABS = [
  { key: "support", href: "/university/support", icon: LifeBuoy },
  { key: "privacy", href: "/university/privacy", icon: Lock },
  { key: "abuse", href: "/university/abuse", icon: ShieldAlert },
] as const;

/**
 * Cross-linking sub-nav for the three Platform Trust surfaces (ADR-0014,
 * E36: support console, privacy admin, abuse triage). Each is gated
 * independently at the service layer (`support:*`/`privacy:*`/`abuse:*`); a
 * staff member without one noun still sees the tab (nav is not permission
 * filtered client-side) but gets a clean permission empty-state on click.
 */
export function TrustTabs() {
  const t = useTranslations("platformTrust");
  const pathname = usePathname();

  return (
    <div
      role="tablist"
      aria-label={t("tabsLabel")}
      className="mb-5 flex gap-2 overflow-x-auto"
    >
      {TABS.map((tab) => {
        const active = pathname.startsWith(tab.href);
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
            <Icon aria-hidden className="size-4" />
            {t(tab.key)}
          </Link>
        );
      })}
    </div>
  );
}
