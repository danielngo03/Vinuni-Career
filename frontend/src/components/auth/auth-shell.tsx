"use client";

import { Link } from "@/i18n/navigation";
import { BrandMark } from "@/components/layout/brand-mark";
import { LanguageSwitcher } from "@/components/layout/language-switcher";
import { ThemeSwitcher } from "@/components/layout/theme-switcher";
import { cn } from "@/lib/utils";

export function AuthShell({
  title,
  subtitle,
  children,
  footer,
  beforeTitle,
  showLogo = true,
  className,
}: {
  title: string;
  subtitle?: string;
  children: React.ReactNode;
  footer?: React.ReactNode;
  beforeTitle?: React.ReactNode;
  showLogo?: boolean;
  className?: string;
}) {
  return (
    <div className="flex min-h-dvh bg-[var(--bg-base)] px-3 py-3 text-[var(--text-primary)] sm:px-5 sm:py-5">
      <section
        className={cn(
          "mx-auto flex min-h-[calc(100dvh-1.5rem)] w-full flex-col overflow-hidden rounded-[28px] border border-[var(--border-default)] bg-[var(--surface-card)] px-5 py-5 shadow-[0_18px_60px_rgba(0,0,0,0.08)] sm:min-h-[calc(100dvh-2.5rem)] sm:px-8 sm:py-7 lg:px-12",
          className,
        )}
      >
        <header className="flex items-center justify-between gap-4">
          {showLogo ? (
            <Link
              href="/"
              aria-label="VinUni Career"
              className="rounded-md outline-none focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/40"
            >
              <BrandMark />
            </Link>
          ) : (
            <span />
          )}
          <div className="flex shrink-0 items-center gap-2">
            <LanguageSwitcher />
            <ThemeSwitcher forceLabel />
          </div>
        </header>

        <div className="flex flex-1 items-center justify-center py-10">
          <div className="w-full max-w-[450px]">
            {beforeTitle && <div className="mb-7">{beforeTitle}</div>}
            <div className="mb-7 text-center">
              <h1 className="text-[2rem] font-extrabold leading-[1.05] tracking-tight text-[var(--text-primary)] sm:text-[2.35rem]">
                {title}
              </h1>
              {subtitle && (
                <p className="mt-3 text-sm leading-6 text-[var(--text-secondary)] sm:text-base">
                  {subtitle}
                </p>
              )}
            </div>

            {children}

            {footer && (
              <div className="mt-6 text-center text-sm text-[var(--text-secondary)]">
                {footer}
              </div>
            )}
          </div>
        </div>
      </section>
    </div>
  );
}
