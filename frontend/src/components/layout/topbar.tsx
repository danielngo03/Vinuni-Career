"use client";

import { useLocale, useTranslations } from "next-intl";
import { Building2, ChevronRight, Menu } from "lucide-react";
import { Sparkle } from "@phosphor-icons/react";
import { LanguageSwitcher } from "./language-switcher";
import { ThemeSwitcher } from "./theme-switcher";
import { BrandMark } from "./brand-mark";
import { AccountMenu } from "./account-menu";
import { NotificationBell } from "@/components/notifications/notification-bell";
import { MessagingBell } from "@/components/messaging/messaging-bell";
import { Link, usePathname } from "@/i18n/navigation";
import { getRouteTitle } from "@/lib/route-titles";
import { navItemsForWorkspace, type Workspace } from "@/config/nav";
import { useUiStore } from "@/stores/ui-store";
import { cn } from "@/lib/utils";

/** Fixed workspace topbar (DESIGN.md §5.4). 60px chrome surface, labeled
 * notification/message pills, and the account dropdown (settings + sign-out). */
export function Topbar({
  persona,
  onAiClick,
  aiActive,
}: {
  persona: Workspace;
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
  const isAdmin = persona === "admin";
  const base = `/${persona}`;
  // The Platform Admin console has no dashboard / personal inbox — its "home" is
  // the platform overview, and it links back to University Operations for those.
  const homeHref = isAdmin ? `${base}/platform-overview` : `${base}/dashboard`;
  const homeKey = isAdmin ? "adminConsole" : "dashboard";
  const homeLabel = tNav(homeKey);
  const navItems = navItemsForWorkspace(persona);
  const currentItem =
    pathname === `${base}/messages` || pathname.startsWith(`${base}/messages/`)
      ? { key: "messages" }
      : pathname === `${base}/notifications` || pathname.startsWith(`${base}/notifications/`)
        ? { key: "notifications" }
      : pathname === `${base}/settings` || pathname.startsWith(`${base}/settings/`)
        ? { key: "settings" }
        : navItems.find((item) => {
            const href = item.absolute ? item.href : `${base}${item.href}`;
            return pathname === href || pathname.startsWith(`${href}/`);
          });
  const currentKey = currentItem?.key ?? homeKey;
  const isDashboard = pathname === homeHref;
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
            : homeHref;
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
            {homeLabel}
          </span>
        ) : (
          <>
            <Link
              href={homeHref}
              className="truncate font-medium text-[var(--text-muted)] outline-none transition-colors hover:text-[var(--text-primary)] focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/30"
            >
              {homeLabel}
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
        {isAdmin ? (
          // The admin console has no personal inbox; offer a clear jump back to
          // the University Operations shell where notifications/messages live.
          <Link
            href="/university/dashboard"
            className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--border-default)] bg-[var(--surface-card)] px-3 py-1.5 text-sm font-semibold text-[var(--text-secondary)] outline-none transition-colors hover:bg-[var(--bg-subtle)] hover:text-[var(--text-primary)] focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/30"
          >
            <Building2 aria-hidden strokeWidth={1.8} className="size-4" />
            <span className="hidden sm:inline">{tNav("universityOps")}</span>
          </Link>
        ) : (
          <>
            <NotificationBell variant="labeled" href={`${base}/notifications`} />
            <MessagingBell variant="labeled" href={`${base}/messages`} />
          </>
        )}
        {onAiClick && (
          <button
            type="button"
            aria-label={tNav("aiAssistant")}
            aria-haspopup="dialog"
            aria-expanded={aiActive ?? false}
            title={tNav("aiAssistant")}
            onClick={onAiClick}
            className={cn(
              "relative inline-flex size-9 items-center justify-center rounded-lg border outline-none transition-colors duration-200 focus-visible:ring-2 focus-visible:ring-[var(--ai-accent)]/50",
              aiActive
                ? "border-[var(--ai-accent)] bg-[var(--ai-accent)] text-white shadow-[var(--shadow-teal)] hover:bg-[var(--ai-accent-strong)]"
                : "border-[var(--ai-accent-ring)] bg-[var(--ai-accent-surface)] text-[var(--ai-accent-strong)] shadow-[var(--ai-chip-shadow)] hover:border-[var(--ai-accent)] hover:bg-[var(--ai-accent-surface-hover)]",
            )}
          >
            <Sparkle
              aria-hidden
              weight="fill"
              className={cn("size-5", aiActive ? "text-white" : "text-[var(--ai-accent-strong)]")}
            />
          </button>
        )}
        <AccountMenu
          settingsHref={isAdmin ? "/university/settings" : `${base}/settings`}
          showName
        />
      </div>
    </header>
  );
}
