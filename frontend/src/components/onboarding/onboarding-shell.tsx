"use client";

import { useTranslations } from "next-intl";
import {
  CheckCircle,
  Clock,
  IdentificationBadge,
  ShieldCheck,
  SignOut,
} from "@phosphor-icons/react";
import { Link, useRouter } from "@/i18n/navigation";
import { BrandMark } from "@/components/layout/brand-mark";
import { LanguageSwitcher } from "@/components/layout/language-switcher";
import { ThemeSwitcher } from "@/components/layout/theme-switcher";
import { useAuthStore } from "@/stores/auth-store";

interface OnboardingShellProps {
  children: React.ReactNode;
  title: string;
  subtitle?: string;
  step?: number;
  totalSteps?: number;
}

export function OnboardingShell({
  children,
  title,
  subtitle,
  step,
  totalSteps,
}: OnboardingShellProps) {
  const t = useTranslations("onboarding");
  const router = useRouter();
  const signOut = useAuthStore((s) => s.signOut);
  const showProgress = step !== undefined && totalSteps !== undefined;
  const pct = showProgress ? Math.round((step / totalSteps) * 100) : 0;
  const nextSteps = [t("step1"), t("step2"), t("step3")];

  async function handleSignOut() {
    await signOut();
    router.replace("/auth/login");
  }

  return (
    <div className="min-h-dvh bg-[var(--bg-base)] px-3 py-3 text-[var(--text-primary)] sm:px-5 sm:py-5">
      <div className="mx-auto grid min-h-[calc(100dvh-1.5rem)] w-full max-w-[1280px] overflow-hidden rounded-[28px] border border-[var(--border-default)] bg-[var(--surface-card)] shadow-[0_18px_60px_rgba(0,0,0,0.08)] lg:grid-cols-[minmax(0,0.94fr)_minmax(380px,0.76fr)] sm:min-h-[calc(100dvh-2.5rem)]">
        <section className="flex min-h-[calc(100dvh-1.5rem)] flex-col px-5 py-5 sm:min-h-[calc(100dvh-2.5rem)] sm:px-8 sm:py-7 lg:px-10 xl:px-12">
          <header className="flex items-center justify-between gap-4">
            <Link
              href="/"
              aria-label="VinUni Career"
              className="rounded-md outline-none focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/40"
            >
              <BrandMark />
            </Link>
            <div className="flex shrink-0 items-center gap-2">
              <LanguageSwitcher />
              <ThemeSwitcher forceLabel />
              <button
                type="button"
                onClick={handleSignOut}
                className="inline-flex h-10 items-center gap-2 rounded-full border border-[var(--border-default)] bg-[var(--surface-card)] px-3 text-sm font-semibold text-[var(--text-secondary)] outline-none transition-colors hover:bg-[var(--bg-subtle)] hover:text-[var(--text-primary)] focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/35"
              >
                <SignOut aria-hidden weight="bold" className="size-4" />
                <span className="hidden sm:inline">{t("signOut")}</span>
              </button>
            </div>
          </header>

          <div className="flex flex-1 items-center justify-center py-10">
            <div className="w-full max-w-[560px]">
              {showProgress && (
                <div className="mb-7">
                  <div className="mb-2 flex items-center justify-between gap-3 text-xs font-bold uppercase tracking-[0.12em] text-[var(--text-muted)]">
                    <span>{t("setupAccount")}</span>
                    <span>{t("stepProgress", { step: step!, total: totalSteps! })}</span>
                  </div>
                  <div className="h-2 overflow-hidden rounded-full bg-[var(--bg-subtle)]">
                    <div
                      className="h-full rounded-full bg-[var(--btn-primary-bg)] transition-all duration-500"
                      style={{ width: `${pct}%` }}
                    />
                  </div>
                </div>
              )}

              <div className="mb-7">
                <h1 className="text-[2rem] font-extrabold leading-[1.05] tracking-tight text-[var(--text-primary)] sm:text-[2.35rem]">
                  {title}
                </h1>
                {subtitle && (
                  <p className="mt-3 text-sm leading-6 text-[var(--text-secondary)] sm:text-base">
                    {subtitle}
                  </p>
                )}
              </div>

              <div>{children}</div>
            </div>
          </div>
        </section>

        <aside className="hidden min-h-full border-l border-[var(--border-default)] bg-[var(--surface-secondary)] p-4 lg:block">
          <div className="flex h-full flex-col justify-between rounded-[24px] border border-[var(--border-default)] bg-[var(--surface-card)] p-6 shadow-[0_10px_30px_rgba(0,0,0,0.05)]">
            <div>
              <span className="inline-flex items-center gap-2 rounded-full border border-[var(--border-default)] bg-[var(--bg-subtle)] px-3 py-1.5 text-xs font-extrabold uppercase tracking-[0.12em] text-[var(--text-secondary)]">
                <IdentificationBadge aria-hidden weight="duotone" className="size-4" />
                VinUni Career
              </span>
              <h2 className="mt-8 text-3xl font-extrabold leading-tight tracking-tight text-[var(--text-primary)]">
                {t("asideTitle")}
              </h2>
              <p className="mt-4 text-sm leading-6 text-[var(--text-secondary)]">
                {t("asideBody")}
              </p>

              <div className="mt-8 space-y-3">
                {nextSteps.map((item, index) => (
                  <div
                    key={item}
                    className="flex items-center gap-3 rounded-[16px] border border-[var(--border-default)] bg-[var(--bg-subtle)] px-3.5 py-3"
                  >
                    <span className="flex size-8 shrink-0 items-center justify-center rounded-full bg-[var(--surface-card)] text-sm font-extrabold text-[var(--text-primary)]">
                      {index + 1}
                    </span>
                    <span className="text-sm font-semibold text-[var(--text-primary)]">
                      {item}
                    </span>
                  </div>
                ))}
              </div>
            </div>

            <div className="rounded-[18px] border border-[var(--border-default)] bg-[var(--bg-subtle)] p-4">
              <div className="flex items-start gap-3">
                <span className="flex size-10 shrink-0 items-center justify-center rounded-full bg-[var(--btn-primary-bg)] text-[var(--btn-primary-fg)]">
                  <ShieldCheck aria-hidden weight="duotone" className="size-5" />
                </span>
                <div>
                  <p className="text-sm font-bold text-[var(--text-primary)]">
                    {t("securityTitle")}
                  </p>
                  <p className="mt-1 text-xs leading-5 text-[var(--text-secondary)]">
                    {t("securityBody")}
                  </p>
                </div>
              </div>
              <div className="mt-4 grid grid-cols-2 gap-2 text-xs font-semibold text-[var(--text-secondary)]">
                <span className="inline-flex items-center gap-1.5 rounded-full bg-[var(--surface-card)] px-2.5 py-1.5">
                  <CheckCircle aria-hidden weight="fill" className="size-3.5" />
                  {t("securityTagRbac")}
                </span>
                <span className="inline-flex items-center gap-1.5 rounded-full bg-[var(--surface-card)] px-2.5 py-1.5">
                  <Clock aria-hidden weight="duotone" className="size-3.5" />
                  {t("securityTagAudit")}
                </span>
              </div>
            </div>
          </div>
        </aside>
      </div>
    </div>
  );
}
