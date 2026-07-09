"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import {
  CircleNotch,
  GearSix,
  List,
  Receipt,
  SignOut,
  SquaresFour,
  UserCircle,
} from "@phosphor-icons/react";
import { Link, usePathname, useRouter } from "@/i18n/navigation";
import { Sheet } from "@/components/ui";
import { LanguageSwitcher } from "./language-switcher";
import { SavedButton } from "./saved-button";
import { getPersonaAccountRoutes } from "./public-auth-actions";
import { PUBLIC_PRIMARY_NAV } from "./public-nav-config";
import { useAuthStore } from "@/stores/auth-store";

/**
 * Mobile (<md) public navigation. A hamburger opens the shared `Sheet` drawer
 * exposing the full primary nav, the Saved affordance, language switch, and
 * login/register — closing the "375px has no browse nav" gap (SCREEN_SPECS §1.1
 * mobile layout). Reuses the same `Sheet` primitive as WorkspaceShell.
 */
export function PublicMobileNav() {
  const tNav = useTranslations("nav");
  const tCommon = useTranslations("common");
  const [open, setOpen] = useState(false);
  const pathname = usePathname();
  const router = useRouter();
  const status = useAuthStore((s) => s.status);
  const user = useAuthStore((s) => s.user);
  const signOut = useAuthStore((s) => s.signOut);
  const routes = getPersonaAccountRoutes(user?.persona);
  const showSaved = status !== "authenticated" || user?.persona === "student";

  // Close on route change.
  useEffect(() => {
    setOpen(false);
  }, [pathname]);

  async function handleSignOut() {
    setOpen(false);
    await signOut();
    router.replace("/");
  }

  return (
    <div className="min-[1360px]:hidden">
      <button
        type="button"
        onClick={() => setOpen(true)}
        aria-label={tNav("openMenu")}
        aria-expanded={open}
        className="inline-flex size-9 items-center justify-center rounded-lg text-[var(--text-secondary)] outline-none transition-colors hover:bg-[var(--bg-subtle)] hover:text-[var(--text-primary)] focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/40"
      >
        <List aria-hidden weight="bold" className="size-5" />
      </button>

      <Sheet
        open={open}
        onClose={() => setOpen(false)}
        side="left"
        title={tNav("home")}
        closeLabel={tNav("closeMenu")}
      >
        <nav aria-label={tNav("home")} className="flex flex-col gap-0.5">
          {PUBLIC_PRIMARY_NAV.map((item) => (
            <Link
              key={item.key}
              href={item.href}
              className="rounded-lg px-3 py-2.5 text-sm font-semibold text-[var(--text-primary)] outline-none hover:bg-[var(--bg-subtle)] focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/40"
            >
              {tNav(item.key)}
            </Link>
          ))}
        </nav>

        {showSaved && (
          <>
            <div className="my-3 border-t border-[var(--border-default)]" />
            <SavedButton variant="row" />
          </>
        )}

        <div className="my-3 border-t border-[var(--border-default)]" />
        {status === "unknown" ? (
          <div className="flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium text-[var(--text-secondary)]">
            <CircleNotch
              aria-hidden
              className="size-5 animate-spin text-[var(--brand-primary)]"
            />
            {tCommon("loading")}
          </div>
        ) : status === "authenticated" ? (
          <div className="flex flex-col gap-1">
            <div className="mb-1 flex items-center gap-3 rounded-lg bg-[var(--bg-subtle)] px-3 py-2.5">
              <UserCircle
                aria-hidden
                weight="duotone"
                className="size-6 shrink-0 text-[var(--brand-primary)]"
              />
              <div className="min-w-0">
                <p className="truncate text-sm font-semibold text-[var(--text-primary)]">
                  {user?.name ?? tNav("userMenu")}
                </p>
                {user?.email && (
                  <p className="truncate text-xs text-[var(--text-muted)]">
                    {user.email}
                  </p>
                )}
              </div>
            </div>
            <Link
              href={routes.dashboardHref}
              className="flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-semibold text-[var(--text-primary)] outline-none hover:bg-[var(--bg-subtle)] focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/40"
            >
              <SquaresFour aria-hidden weight="duotone" className="size-5 shrink-0" />
              {tNav("dashboard")}
            </Link>
            <Link
              href={routes.billingHref}
              className="flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium text-[var(--text-secondary)] outline-none hover:bg-[var(--bg-subtle)] hover:text-[var(--text-primary)] focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/40"
            >
              <Receipt aria-hidden weight="duotone" className="size-5 shrink-0" />
              {tNav("billing")}
            </Link>
            <Link
              href={routes.settingsHref}
              className="flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium text-[var(--text-secondary)] outline-none hover:bg-[var(--bg-subtle)] hover:text-[var(--text-primary)] focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/40"
            >
              <GearSix aria-hidden weight="duotone" className="size-5 shrink-0" />
              {tNav("settings")}
            </Link>
            <button
              type="button"
              onClick={handleSignOut}
              className="flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left text-sm font-medium text-[var(--text-secondary)] outline-none hover:bg-[var(--bg-subtle)] hover:text-[var(--brand-red)] focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/40"
            >
              <SignOut aria-hidden weight="duotone" className="size-5 shrink-0" />
              {tNav("logout")}
            </button>
          </div>
        ) : (
          <div className="flex flex-col gap-2">
            <Link
              href="/auth/login"
              className="inline-flex h-10 items-center justify-center rounded-lg border border-[var(--border-default)] bg-[var(--surface-card)] px-4 text-sm font-semibold text-[var(--text-primary)] outline-none transition-colors hover:bg-[var(--bg-subtle)] focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/40"
            >
              {tNav("login")}
            </Link>
            <Link
              href="/auth/register"
              className="inline-flex h-10 items-center justify-center rounded-lg bg-[var(--btn-primary-bg)] px-4 text-sm font-semibold text-[var(--btn-primary-fg)] shadow-[var(--shadow-brand)] outline-none transition-colors hover:bg-[var(--btn-primary-hover)] focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/40"
            >
              {tNav("register")}
            </Link>
          </div>
        )}

        <div className="mt-4">
          <LanguageSwitcher />
        </div>
      </Sheet>
    </div>
  );
}
