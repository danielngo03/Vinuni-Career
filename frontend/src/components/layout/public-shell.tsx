"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { Link, usePathname } from "@/i18n/navigation";
import { cn } from "@/lib/utils";
import { BrandMark } from "./brand-mark";
import { LanguageSwitcher } from "./language-switcher";
import { ThemeSwitcher } from "./theme-switcher";
import { LoginModal } from "./login-modal";
import { AppFooter } from "./footer";
import { CompanyMegaMenu } from "./company-mega-menu";
import { EventsMegaMenu } from "./events-mega-menu";
import { JobsMegaMenu } from "./jobs-mega-menu";
import { PublicMobileNav } from "./public-mobile-nav";
import { PublicAuthActions } from "./public-auth-actions";
import { FloatingActionRail } from "./floating-action-rail";
import { PUBLIC_PRIMARY_NAV } from "./public-nav-config";

export function PublicShell({ children }: { children: React.ReactNode }) {
  const t = useTranslations();
  const pathname = usePathname();
  const [scrolled, setScrolled] = useState(false);

  useEffect(() => {
    const handler = () => setScrolled(window.scrollY > 8);
    handler();
    window.addEventListener("scroll", handler, { passive: true });
    return () => window.removeEventListener("scroll", handler);
  }, []);

  return (
    <div className="flex min-h-dvh flex-col bg-[var(--bg-base)]">
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-[70] focus:rounded-lg focus:bg-[var(--brand-primary)] focus:px-4 focus:py-2 focus:text-sm focus:font-semibold focus:text-white"
      >
        {t("common.skipToContent")}
      </a>

      <header
        className={cn(
          "sticky top-0 z-30 border-b border-[var(--border-default)] bg-[var(--surface-card)] transition-shadow duration-300",
          scrolled
            ? "shadow-[0_2px_18px_rgba(11,34,57,0.08)]"
            : "shadow-none",
        )}
      >
        {/* `relative` anchors the full-width Companies mega-menu panel. */}
        <div className="relative mx-auto flex h-[68px] max-w-[1400px] items-center gap-4 px-4 lg:px-6">

          {/* Logo */}
          <Link
            href="/"
            aria-label="VinUni Career"
            className="shrink-0 rounded-md outline-none focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/40"
          >
            <BrandMark />
          </Link>

          {/* Enterprise nav — flat, with underline active state like DESIGN_EXAMPLE.
              Left-aligned right after the logo (not centered in the leftover
              space), since the auth-actions cluster on the right is wider
              than the logo and dead-centering would visually skew the nav
              left of true page-center. */}
          <div className="hidden min-w-0 flex-1 items-center min-[1360px]:flex">
            <nav
              aria-label={t("nav.home")}
              className="ml-8 flex h-[68px] items-center gap-5 xl:gap-7"
            >
              {PUBLIC_PRIMARY_NAV.map((item) => {
                const isActive =
                  item.href === "/"
                    ? pathname === "/"
                    : pathname === item.href || pathname.startsWith(item.href + "/");

                if (item.mega === "jobs") {
                  return <JobsMegaMenu key={item.key} isActive={isActive} />;
                }
                if (item.mega === "companies") {
                  return <CompanyMegaMenu key={item.key} isActive={isActive} />;
                }
                if (item.mega === "events") {
                  return <EventsMegaMenu key={item.key} isActive={isActive} />;
                }

                return (
                  <Link
                    key={item.key}
                    href={item.href}
                    aria-current={isActive ? "page" : undefined}
                    className={cn(
                      "relative inline-flex h-full shrink-0 items-center whitespace-nowrap px-0 text-sm font-semibold outline-none transition-colors",
                      "focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/40",
                      "after:absolute after:inset-x-0 after:bottom-0 after:h-[2px] after:origin-center after:rounded-full after:bg-[var(--brand-primary)] after:transition-transform after:duration-200",
                      isActive
                        ? "text-[var(--brand-primary)] after:scale-x-100"
                        : "text-[var(--text-secondary)] after:scale-x-0 hover:text-[var(--brand-navy)] hover:after:scale-x-100",
                    )}
                  >
                    {t(`nav.${item.key}`)}
                  </Link>
                );
              })}
            </nav>
          </div>

          {/* Auth + language */}
          <div className="ml-auto flex shrink-0 items-center gap-2">
            <LanguageSwitcher compact hoverCompact />
            <ThemeSwitcher hoverCompact />
            <PublicAuthActions />
            <PublicMobileNav />
          </div>
        </div>
      </header>

      <main id="main-content" tabIndex={-1} className="flex-1 outline-none">
        {children}
      </main>

      <AppFooter />
      <FloatingActionRail />
      <LoginModal />
    </div>
  );
}
