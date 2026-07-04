"use client";

import { useEffect } from "react";
import { useTranslations } from "next-intl";
import { CircleNotch } from "@phosphor-icons/react";
import { Link, usePathname, useRouter } from "@/i18n/navigation";
import { useQuery } from "@tanstack/react-query";
import { BrandMark } from "./brand-mark";
import { LanguageSwitcher } from "./language-switcher";
import { ThemeSwitcher } from "./theme-switcher";
import { AccountMenu } from "./account-menu";
import { StudentMobileNav } from "./student-mobile-nav";
import { FloatingActionRail } from "./floating-action-rail";
import { AppFooter } from "./footer";
import { LoginModal } from "./login-modal";
import { NotificationBell } from "@/components/notifications/notification-bell";
import { MessagingBell } from "@/components/messaging/messaging-bell";
import { STUDENT_PRIMARY_NAV, studentHref } from "@/config/nav";
import { useAuthStore } from "@/stores/auth-store";
import { invitationsApi } from "@/lib/api";
import { cn } from "@/lib/utils";

function InvitationBadge() {
  const isAuthed = useAuthStore((s) => s.status === "authenticated");
  const { data } = useQuery({
    queryKey: ["student-invitations-pending-count"],
    queryFn: () => invitationsApi.listMine({ status: "pending" }),
    enabled: isAuthed,
    staleTime: 30_000,
    refetchInterval: 60_000,
  });
  const count = data?.filter((i) => i.status === "pending").length ?? 0;
  if (!isAuthed || count === 0) return null;
  return (
    <span
      aria-label={`${count} pending`}
      className="ml-1 inline-flex min-w-[18px] items-center justify-center rounded-full bg-[var(--brand-primary)] px-1 text-[10px] font-bold leading-[18px] text-white"
    >
      {count > 9 ? "9+" : count}
    </span>
  );
}

const SETTINGS_HREF = "/student/settings";
const BILLING_HREF = "/student/billing";

/**
 * Signed-in STUDENT shell. Inherits the public marketplace top-nav pattern
 * (brand + horizontal nav + language + saved + notifications + account menu +
 * mobile drawer) rather than the admin-style sidebar used by partner/university
 * (SCREEN_SPECS §1: "signed-in marketplace top nav inherited from the public
 * gateway"; frontend.md: "Do not default to an admin-style sidebar for student
 * desktop"). Employer-acquisition items are intentionally omitted.
 *
 * Route guard mirrors `WorkspaceShell`: guests are redirected to login with a
 * `returnTo`, and a loading state renders while the session hydrates.
 */
export function StudentShell({ children }: { children: React.ReactNode }) {
  const t = useTranslations("common");
  const tNav = useTranslations("nav");
  const status = useAuthStore((s) => s.status);
  const pathname = usePathname();
  const router = useRouter();

  useEffect(() => {
    if (status === "guest") {
      router.replace(`/auth/login?returnTo=${encodeURIComponent(pathname)}`);
    }
  }, [status, pathname, router]);

  if (status !== "authenticated") {
    return (
      <div className="flex min-h-dvh flex-col items-center justify-center gap-4 bg-[var(--bg-base)] px-4">
        <BrandMark />
        <div className="flex items-center gap-2 text-sm text-[var(--text-secondary)]">
          <CircleNotch
            aria-hidden
            className="size-4 animate-spin text-[var(--brand-primary)]"
          />
          <span role="status">
            {status === "guest" ? t("redirecting") : t("loading")}
          </span>
        </div>
      </div>
    );
  }

  function isActive(href: string) {
    return pathname === href || pathname.startsWith(`${href}/`);
  }

  const isFullCanvasRoute =
    pathname === "/student/messages" ||
    pathname.startsWith("/student/messages/") ||
    pathname === "/student/notifications" ||
    pathname.startsWith("/student/notifications/");

  return (
    <div className="flex min-h-dvh flex-col bg-[var(--bg-base)]">
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-[70] focus:rounded-lg focus:bg-[var(--brand-primary)] focus:px-4 focus:py-2 focus:text-sm focus:font-semibold focus:text-white"
      >
        {t("skipToContent")}
      </a>

      <header className="sticky top-0 z-30 border-b border-[var(--border-default)] bg-[var(--surface-card)] shadow-[0_1px_14px_rgba(11,34,57,0.05)]">
        <div className="mx-auto flex h-[68px] max-w-[1400px] items-center gap-3 px-4 lg:px-6">
          <Link
            href="/student/dashboard"
            aria-label="VinUni Career"
            className="shrink-0 outline-none"
          >
            <BrandMark />
          </Link>

          <nav
            aria-label={tNav("home")}
            className="ml-8 hidden h-[68px] items-center gap-7 md:flex"
          >
            {STUDENT_PRIMARY_NAV.map((item) => {
              const href = studentHref(item);
              const active = isActive(href);
              return (
                <Link
                  key={item.key}
                  href={href}
                  aria-current={active ? "page" : undefined}
                  className={cn(
                    "relative inline-flex h-full items-center px-0 text-sm font-semibold outline-none transition-colors focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/40",
                    "after:absolute after:inset-x-0 after:bottom-0 after:h-[2px] after:origin-center after:rounded-full after:bg-[var(--brand-primary)] after:transition-transform after:duration-200",
                    active
                      ? "text-[var(--brand-primary)] after:scale-x-100"
                      : "text-[var(--text-secondary)] after:scale-x-0 hover:text-[var(--brand-navy)] hover:after:scale-x-100",
                  )}
                >
                  {tNav(item.key)}
                  {item.key === "invitations" && <InvitationBadge />}
                </Link>
              );
            })}
          </nav>

          <div className="ml-auto flex items-center gap-1.5 sm:gap-2">
            <div className="hidden sm:block">
              <LanguageSwitcher compact hoverCompact />
            </div>
            <div className="hidden sm:block">
              <ThemeSwitcher hoverCompact />
            </div>
            {/* Saved lives in the floating quick-action rail; the header keeps
                badge indicators (messages, notifications) — realism spec §3. */}
            <MessagingBell href="/student/messages" />
            <NotificationBell href="/student/notifications" />
            <div className="hidden md:block">
              <AccountMenu settingsHref={SETTINGS_HREF} billingHref={BILLING_HREF} />
            </div>
            <StudentMobileNav
              settingsHref={SETTINGS_HREF}
              billingHref={BILLING_HREF}
            />
          </div>
        </div>
      </header>

      <main
        id="main-content"
        tabIndex={-1}
        className={cn(
          "flex-1 outline-none",
          isFullCanvasRoute ? "flex min-h-0 p-0" : "px-4 py-6 lg:px-6",
        )}
      >
        <div
          className={cn(
            "w-full",
            isFullCanvasRoute ? "min-h-0 flex-1" : "mx-auto max-w-[1400px]",
          )}
        >
          {children}
        </div>
      </main>

      <AppFooter />
      <FloatingActionRail />
      <LoginModal />
    </div>
  );
}
