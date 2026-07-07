"use client";

import { useTranslations } from "next-intl";
import { Link, usePathname } from "@/i18n/navigation";
import { cn } from "@/lib/utils";
import { CompanyMegaMenu } from "./company-mega-menu";
import { EventsMegaMenu } from "./events-mega-menu";
import { JobsMegaMenu } from "./jobs-mega-menu";
import { PUBLIC_PRIMARY_NAV } from "./public-nav-config";

/**
 * Shared desktop primary navigation for the marketplace surfaces. Used by BOTH
 * the public shell and the signed-in student shell so the two headers never
 * drift (the student experience inherits the public marketplace top nav — only
 * the right-hand actions differ by auth state). Items with a `mega` marker
 * render a discovery mega-menu; everything else is a flat underlined link.
 */
export function MarketplaceNav() {
  const t = useTranslations();
  const pathname = usePathname();

  return (
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
  );
}
