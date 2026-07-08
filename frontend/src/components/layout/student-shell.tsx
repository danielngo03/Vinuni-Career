"use client";

import { useEffect } from "react";
import { useTranslations } from "next-intl";
import { CircleNotch } from "@phosphor-icons/react";
import { Link, usePathname, useRouter } from "@/i18n/navigation";
import { BrandMark } from "./brand-mark";
import { LanguageSwitcher } from "./language-switcher";
import { ThemeSwitcher } from "./theme-switcher";
import { MarketplaceNav } from "./marketplace-nav";
import { PublicAuthActions } from "./public-auth-actions";
import { PublicMobileNav } from "./public-mobile-nav";
import { AppFooter } from "./footer";
import { LoginModal } from "./login-modal";
import { useAuthStore } from "@/stores/auth-store";
import { cn } from "@/lib/utils";

/**
 * Signed-in STUDENT shell. It renders the EXACT same marketplace header as the
 * public shell (`MarketplaceNav` + `PublicAuthActions` + `PublicMobileNav`), so
 * the two never drift: the primary nav stays the four public items (Việc làm /
 * Doanh nghiệp / Sự kiện / Tạo CV) and the signed-in extras — notifications,
 * messages, saved, AI, plus Overview/Profile/Applications/Invitations — live in
 * the right-hand actions and the account (avatar) menu, not as top-nav tabs.
 *
 * The only student-specific responsibilities here are the route guard (guests →
 * login with returnTo; wrong persona → their own home) and the full-canvas main
 * used by the messages/notifications pages.
 */
export function StudentShell({ children }: { children: React.ReactNode }) {
  const t = useTranslations("common");
  const status = useAuthStore((s) => s.status);
  const user = useAuthStore((s) => s.user);
  const pathname = usePathname();
  const router = useRouter();

  useEffect(() => {
    if (status === "guest") {
      router.replace(`/auth/login?returnTo=${encodeURIComponent(pathname)}`);
      return;
    }
    if (status === "authenticated" && user && user.persona !== "student") {
      router.replace(`/${user.persona}`);
    }
  }, [status, user, pathname, router]);

  // Wait for hydration; reject wrong-persona access (UX guard — backend RBAC is
  // the actual security boundary).
  if (status !== "authenticated" || (user && user.persona !== "student")) {
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
        <div className="relative mx-auto flex h-[68px] max-w-[1400px] items-center gap-4 px-4 lg:px-6">
          <Link href="/" aria-label="VinUni Career" className="shrink-0 outline-none">
            <BrandMark />
          </Link>

          {/* Shared marketplace nav — identical to the public shell. */}
          <MarketplaceNav />

          <div className="ml-auto flex shrink-0 items-center gap-2">
            <LanguageSwitcher compact hoverCompact />
            <ThemeSwitcher hoverCompact />
            <PublicAuthActions />
            <PublicMobileNav />
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
      <LoginModal />
    </div>
  );
}
