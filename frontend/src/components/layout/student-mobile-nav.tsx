"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { List, GearSix, Receipt, SignOut } from "@phosphor-icons/react";
import { Link, usePathname, useRouter } from "@/i18n/navigation";
import { Sheet } from "@/components/ui";
import { LanguageSwitcher } from "./language-switcher";
import { SavedButton } from "./saved-button";
import { STUDENT_PRIMARY_NAV, studentHref } from "@/config/nav";
import { useAuthStore } from "@/stores/auth-store";
import { cn } from "@/lib/utils";

/**
 * Mobile (<md) navigation for the signed-in student top-nav shell. A hamburger
 * opens the shared `Sheet` drawer (same focus-trap primitive as the public
 * mobile nav) exposing the student items, Saved, settings, sign-out, and the
 * language switch — so the marketplace top-nav stays reachable at 375px.
 */
export function StudentMobileNav({
  settingsHref,
  billingHref,
}: {
  settingsHref: string;
  billingHref?: string;
}) {
  const tNav = useTranslations("nav");
  const pathname = usePathname();
  const router = useRouter();
  const signOut = useAuthStore((s) => s.signOut);
  const [open, setOpen] = useState(false);

  // Close on route change.
  useEffect(() => {
    setOpen(false);
  }, [pathname]);

  function isActive(href: string) {
    return pathname === href || pathname.startsWith(`${href}/`);
  }

  async function handleSignOut() {
    setOpen(false);
    await signOut();
    router.replace("/");
  }

  return (
    <div className="md:hidden">
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
          {STUDENT_PRIMARY_NAV.map((item) => {
            const href = studentHref(item);
            const active = isActive(href);
            return (
              <Link
                key={item.key}
                href={href}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-semibold outline-none focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/40",
                  active
                    ? "bg-[var(--brand-primary)]/10 text-[var(--brand-primary)]"
                    : "text-[var(--text-primary)] hover:bg-[var(--bg-subtle)]",
                )}
              >
                <item.icon aria-hidden weight="duotone" className="size-5 shrink-0" />
                {tNav(item.key)}
              </Link>
            );
          })}
        </nav>

        <div className="my-3 border-t border-[var(--border-default)]" />
        <SavedButton variant="row" />
        {billingHref && (
          <Link
            href={billingHref}
            className="flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium text-[var(--text-secondary)] outline-none hover:bg-[var(--bg-subtle)] hover:text-[var(--text-primary)] focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/40"
          >
            <Receipt aria-hidden weight="duotone" className="size-5 shrink-0" />
            {tNav("billing")}
          </Link>
        )}
        <Link
          href={settingsHref}
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

        <div className="my-3 border-t border-[var(--border-default)]" />
        <LanguageSwitcher />
      </Sheet>
    </div>
  );
}
