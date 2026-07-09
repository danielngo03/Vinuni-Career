"use client";

import { useLocale, useTranslations } from "next-intl";
import { ChevronRight, Menu, Sparkles } from "lucide-react";
import { LanguageSwitcher } from "./language-switcher";
import { ThemeSwitcher } from "./theme-switcher";
import { BrandMark } from "./brand-mark";
import { AccountMenu } from "./account-menu";
import { NotificationBell } from "@/components/notifications/notification-bell";
import { MessagingBell } from "@/components/messaging/messaging-bell";
import { Link, usePathname } from "@/i18n/navigation";
import { getRouteTitle } from "@/lib/route-titles";
import { WORKSPACE_NAV } from "@/config/nav";
import { useUiStore } from "@/stores/ui-store";
import { cn } from "@/lib/utils";
import type { Persona } from "@/stores/auth-store";

/** Fixed workspace topbar (DESIGN.md §5.4). 60px chrome surface, labeled
 * notification/message pills, and the account dropdown (settings + sign-out). */
export function Topbar({
  persona,
  onAiClick,
  aiActive,
}: {
  persona: Persona;
  /** Toggles the shared workspace AI assistant chat window. */
  onAiClick?: () => void;
  /** When true, the AI assistant button reads as active/open. */
  aiActive?: boolean;
}) {
  const t = useTranslations();
  const tNav = useTranslations("nav");
  const locale = useLocale();
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
  const currentLabel = tNav(currentKey);
  const currentHref =
    currentKey === "messages"
      ? `${base}/messages`
      : currentKey === "notifications"
        ? `${base}/notifications`
        : currentKey === "settings"
          ? `${base}/settings`
          : currentItem && "href" in currentItem
            ? currentItem.absolute
              ? currentItem.href
              : `${base}${currentItem.href}`
            : `${base}/dashboard`;
  const breadcrumbLeaf =
    pathname === "/partner/jobs/new"
      ? tNav("createNew")
      : (() => {
          const routeTitle = getRouteTitle(pathname, locale);
          if (!routeTitle || routeTitle === currentLabel || routeTitle === tNav("dashboard")) {
            return null;
          }
          return routeTitle;
        })();

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
            {breadcrumbLeaf ? (
              <>
                <Link
                  href={currentHref}
                  className="truncate font-medium text-[var(--text-muted)] outline-none transition-colors hover:text-[var(--text-primary)] focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/30"
                >
                  {currentLabel}
                </Link>
                <ChevronRight
                  aria-hidden
                  strokeWidth={1.8}
                  className="size-4 shrink-0 text-[var(--text-muted)]"
                />
                <span className="truncate font-semibold text-[var(--text-primary)]">
                  {breadcrumbLeaf}
                </span>
              </>
            ) : (
              <span className="truncate font-semibold text-[var(--text-primary)]">
                {currentLabel}
              </span>
            )}
          </>
        )}
      </nav>

      <div className="ml-auto flex items-center gap-2">
        <LanguageSwitcher compact />
        <ThemeSwitcher />
        <NotificationBell variant="labeled" href={`/${persona}/notifications`} />
        <MessagingBell variant="labeled" href={`/${persona}/messages`} />
        {onAiClick && (
          <button
            type="button"
            aria-label={tNav("aiAssistant")}
            aria-haspopup="dialog"
            aria-expanded={aiActive ?? false}
            title={tNav("aiAssistant")}
            onClick={onAiClick}
            className={cn(
              "inline-flex h-9 cursor-pointer items-center gap-2 rounded-full border px-3.5 text-[0.8125rem] font-semibold outline-none transition-colors duration-200 focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/40",
              aiActive
                ? "border-[var(--text-primary)] bg-[var(--text-primary)] text-white shadow-[0_8px_18px_rgba(0,0,0,0.12)] hover:bg-black"
                : "border-[var(--border-default)] bg-[var(--surface-card)] text-[var(--text-primary)] hover:border-[var(--border-strong)] hover:bg-[var(--bg-subtle)]",
            )}
          >
            <Sparkles
              aria-hidden
              strokeWidth={1.8}
              className={cn("size-4", aiActive ? "text-white" : "text-[var(--text-secondary)]")}
            />
            <span className="hidden lg:inline">AI</span>
          </button>
        )}
        <AccountMenu
          settingsHref={`/${persona}/settings`}
          showName
          showHelpSupport
        />
      </div>
    </header>
  );
}
