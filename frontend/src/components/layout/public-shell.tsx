"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { Link } from "@/i18n/navigation";
import { cn } from "@/lib/utils";
import { BrandMark } from "./brand-mark";
import { LanguageSwitcher } from "./language-switcher";
import { ThemeSwitcher } from "./theme-switcher";
import { LoginModal } from "./login-modal";
import { AppFooter } from "./footer";
import { MarketplaceNav } from "./marketplace-nav";
import { PublicMobileNav } from "./public-mobile-nav";
import { PublicAuthActions } from "./public-auth-actions";

export function PublicShell({ children }: { children: React.ReactNode }) {
  const t = useTranslations();
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
        className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-[70] focus:rounded-lg focus:bg-[var(--btn-primary-bg)] focus:px-4 focus:py-2 focus:text-sm focus:font-semibold focus:text-[var(--btn-primary-fg)]"
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

          {/* Shared marketplace primary nav (public + student inherit it). */}
          <MarketplaceNav />

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
      <LoginModal />
    </div>
  );
}
