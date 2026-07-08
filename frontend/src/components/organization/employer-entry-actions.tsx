"use client";

import { ArrowRight, CircleNotch, SquaresFour } from "@phosphor-icons/react";
import { useTranslations } from "next-intl";
import { Link } from "@/i18n/navigation";
import { getPersonaAccountRoutes } from "@/components/layout/public-auth-actions";
import { useAuthStore } from "@/stores/auth-store";

export function EmployerEntryActions() {
  const t = useTranslations("employers");
  const tNav = useTranslations("nav");
  const tCommon = useTranslations("common");
  const status = useAuthStore((s) => s.status);
  const persona = useAuthStore((s) => s.user?.persona);
  const routes = getPersonaAccountRoutes(persona);

  if (status === "unknown") {
    return (
      <div className="flex h-11 items-center gap-2 rounded-lg border border-white/20 px-5 text-sm font-semibold text-white/80">
        <CircleNotch aria-hidden className="size-4 animate-spin" />
        {tCommon("loading")}
      </div>
    );
  }

  if (status === "authenticated" && persona === "partner") {
    return (
      <Link
        href={routes.dashboardHref}
        className="inline-flex h-11 items-center justify-center gap-1.5 rounded-lg bg-white px-6 text-sm font-semibold text-[var(--brand-primary)] outline-none transition-colors hover:bg-[var(--blue-50)] focus-visible:ring-2 focus-visible:ring-white"
      >
        <SquaresFour aria-hidden weight="duotone" className="size-4" />
        {tNav("dashboard")}
      </Link>
    );
  }

  return (
    <>
      <Link
        href="/auth/partner-registration"
        className="inline-flex h-11 items-center justify-center gap-1.5 rounded-lg bg-white px-6 text-sm font-semibold text-[var(--brand-primary)] outline-none transition-colors hover:bg-[var(--blue-50)] focus-visible:ring-2 focus-visible:ring-white"
      >
        {t("ctaRegister")}
        <ArrowRight aria-hidden weight="bold" className="size-4" />
      </Link>
      <Link
        href={status === "authenticated" ? routes.dashboardHref : "/auth/login"}
        className="inline-flex h-11 items-center justify-center rounded-lg border border-white/30 px-6 text-sm font-semibold text-white outline-none transition-colors hover:bg-white/10 focus-visible:ring-2 focus-visible:ring-white"
      >
        {status === "authenticated" ? tNav("dashboard") : t("ctaLogin")}
      </Link>
    </>
  );
}
