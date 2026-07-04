"use client";

import { CircleNotch, SquaresFour } from "@phosphor-icons/react";
import { useTranslations } from "next-intl";
import { Link } from "@/i18n/navigation";
import { useAuthStore, type Persona } from "@/stores/auth-store";
import { AccountMenu } from "./account-menu";

export interface PersonaAccountRoutes {
  dashboardHref: string;
  settingsHref: string;
  billingHref: string;
}

export function getPersonaAccountRoutes(
  persona: Persona | null | undefined,
): PersonaAccountRoutes {
  const normalized = persona ?? "student";
  return {
    dashboardHref: `/${normalized}/dashboard`,
    settingsHref: `/${normalized}/settings`,
    billingHref: `/${normalized}/billing`,
  };
}

/**
 * Auth-aware actions for the public marketplace header. This keeps the public
 * shell honest after session hydration: guests see login/register; signed-in
 * users get their workspace entry point and account menu.
 */
export function PublicAuthActions() {
  const tNav = useTranslations("nav");
  const tCommon = useTranslations("common");
  const status = useAuthStore((s) => s.status);
  const persona = useAuthStore((s) => s.user?.persona);

  if (status === "unknown") {
    return (
      <div
        aria-label={tCommon("loading")}
        className="hidden h-9 w-[168px] items-center justify-end gap-2 text-[var(--text-muted)] min-[1360px]:flex"
      >
        <CircleNotch aria-hidden className="size-4 animate-spin" />
        <span className="h-2 w-20 rounded-full bg-[var(--bg-subtle)]" />
      </div>
    );
  }

  if (status === "authenticated") {
    const routes = getPersonaAccountRoutes(persona);
    return (
      <div className="hidden items-center gap-2 min-[1360px]:flex">
        <Link
          href={routes.dashboardHref}
          className="inline-flex h-9 items-center gap-2 rounded-full border border-[var(--border-default)] bg-[var(--surface-card)] px-3.5 text-sm font-semibold text-[var(--text-primary)] outline-none transition-colors hover:bg-[var(--bg-subtle)] focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/40"
        >
          <SquaresFour aria-hidden weight="duotone" className="size-4" />
          {tNav("dashboard")}
        </Link>
        <AccountMenu
          settingsHref={routes.settingsHref}
          billingHref={routes.billingHref}
        />
      </div>
    );
  }

  return (
    <>
      <Link
        href="/auth/login"
        className="hidden h-9 items-center rounded-full px-3.5 text-sm font-semibold text-[var(--text-secondary)] outline-none transition-colors hover:bg-[var(--bg-subtle)] hover:text-[var(--brand-navy)] focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/40 min-[1360px]:inline-flex"
      >
        {tNav("login")}
      </Link>
      <Link
        href="/auth/register"
        className="hidden h-9 items-center rounded-full bg-[var(--brand-primary)] px-5 text-sm font-semibold text-white shadow-[var(--shadow-brand)] outline-none transition-colors hover:bg-[var(--blue-700)] focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/40 min-[1360px]:inline-flex"
      >
        {tNav("register")}
      </Link>
    </>
  );
}
