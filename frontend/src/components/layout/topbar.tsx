"use client";

import { useTranslations } from "next-intl";
import { ChevronRight, Menu } from "lucide-react";
import { LanguageSwitcher } from "./language-switcher";
import { ThemeSwitcher } from "./theme-switcher";
import { BrandMark } from "./brand-mark";
import { AccountMenu } from "./account-menu";
import { NotificationBell } from "@/components/notifications/notification-bell";
import { MessagingBell } from "@/components/messaging/messaging-bell";
import { Link, usePathname } from "@/i18n/navigation";
import { WORKSPACE_NAV } from "@/config/nav";
import { useUiStore } from "@/stores/ui-store";
import type { Persona } from "@/stores/auth-store";

/** Fixed workspace topbar (DESIGN.md §5.4). 60px chrome surface, labeled
 * notification/message pills, and the account dropdown (settings + sign-out). */
export function Topbar({ persona }: { persona: Persona }) {
  const t = useTranslations();
  const tNav = useTranslations("nav");
  const pathname = usePathname();
  const setMobileNavOpen = useUiStore((s) => s.setMobileNavOpen);
  const base = `/${persona}`;
  const currentItem =
    pathname === `${base}/messages` || pathname.startsWith(`${base}/messages/`)
      ? { key: "messages" }
      : pathname === `${base}/notifications` || pathname.startsWith(`${base}/notifications/`)
        ? { key: "notifications" }
      : pathname === `${base}/settings` || pathname.startsWith(`${base}/settings/`)
        ? { key: "settings" }
        : WORKSPACE_NAV[persona].find((item) => {
            const href = item.absolute ? item.href : `${base}${item.href}`;
            return pathname === href || pathname.startsWith(`${href}/`);
          });
  const currentKey = currentItem?.key ?? "dashboard";
  const isDashboard = pathname === `${base}/dashboard`;

  return (
    <header className="sticky top-0 z-30 flex h-[60px] items-center gap-3 bg-[#f7f6f2]/95 px-4 backdrop-blur-sm lg:px-6">
      <button
        type="button"
        onClick={() => setMobileNavOpen(true)}
        aria-label={t("nav.openMenu")}
        className="rounded-lg p-2 text-[var(--text-secondary)] outline-none hover:bg-[var(--bg-subtle)] lg:hidden"
      >
        <Menu aria-hidden strokeWidth={1.8} className="size-5" />
      </button>

      <div className="lg:hidden">
        <BrandMark showTagline={false} />
      </div>

      <nav
        aria-label={tNav("home")}
        className="hidden min-w-0 flex-1 items-center gap-1.5 text-sm lg:flex"
      >
        {isDashboard ? (
          <span className="truncate font-semibold text-[var(--text-primary)]">
            {tNav("dashboard")}
          </span>
        ) : (
          <>
            <Link
              href={`${base}/dashboard`}
              className="truncate font-medium text-[var(--text-muted)] outline-none transition-colors hover:text-[var(--text-primary)] focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/30"
            >
              {tNav("dashboard")}
            </Link>
            <ChevronRight
              aria-hidden
              strokeWidth={1.8}
              className="size-4 shrink-0 text-[var(--text-muted)]"
            />
            <span className="truncate font-semibold text-[var(--text-primary)]">
              {tNav(currentKey)}
            </span>
          </>
        )}
      </nav>

      <div className="ml-auto flex items-center gap-2">
        <LanguageSwitcher compact />
        <ThemeSwitcher />
        <NotificationBell variant="labeled" href={`/${persona}/notifications`} />
        <MessagingBell variant="labeled" href={`/${persona}/messages`} />
        <AccountMenu settingsHref={`/${persona}/settings`} showName />
      </div>
    </header>
  );
}
