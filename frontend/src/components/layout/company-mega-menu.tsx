"use client";

import { useEffect, useId, useRef, useState } from "react";
import { useTranslations } from "next-intl";
import { useQuery } from "@tanstack/react-query";
import {
  CaretDown,
  CaretRight,
  ArrowRight,
  Monitor,
  Bank,
  Scales,
  Factory,
  FirstAid,
  GraduationCap,
  Buildings,
  type Icon,
} from "@phosphor-icons/react";
import { Link, usePathname } from "@/i18n/navigation";
import { Skeleton } from "@/components/ui";
import { CompanyAvatar } from "@/components/companies/company-avatar";
import { TrackedItem } from "@/components/discovery/tracked-item";
import { VerifiedBadge } from "@/components/ui/verified-badge";
import { companySignalTags } from "@/lib/discovery/signal-tags";
import { marketplaceApi } from "@/lib/api";
import { cn } from "@/lib/utils";
import { MegaCampaignCard } from "./mega-campaign-card";

const INDUSTRIES: ReadonlyArray<{ key: string; query: string; icon: Icon }> = [
  { key: "it", query: "Công nghệ thông tin", icon: Monitor },
  { key: "finance", query: "Tài chính – Ngân hàng", icon: Bank },
  { key: "consulting", query: "Tư vấn & Kiểm toán", icon: Scales },
  { key: "manufacturing", query: "Sản xuất & Kỹ thuật", icon: Factory },
  { key: "healthcare", query: "Y tế & Dược phẩm", icon: FirstAid },
  { key: "education", query: "Giáo dục & Nghiên cứu", icon: GraduationCap },
];

/**
 * "Công ty" discovery mega-menu. The trigger is a real link to the company
 * directory; hover/focus reveal this discovery layer without hijacking click.
 */
export function CompanyMegaMenu({
  triggerClassName,
  isActive = false,
  pill = false,
}: {
  triggerClassName?: string;
  isActive?: boolean;
  pill?: boolean;
}) {
  const t = useTranslations("companyMenu");
  const tNav = useTranslations("nav");
  const tCompanies = useTranslations("companies");
  const pathname = usePathname();
  const renderId = useId();

  const [open, setOpen] = useState(false);
  const [hasOpened, setHasOpened] = useState(false);
  const triggerRef = useRef<HTMLAnchorElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const closeTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const query = useQuery({
    queryKey: ["marketplace", "overview"],
    queryFn: () => marketplaceApi.overview(),
    enabled: hasOpened,
    retry: false,
    staleTime: 60_000,
  });

  function openMenu() {
    if (closeTimer.current) clearTimeout(closeTimer.current);
    setHasOpened(true);
    setOpen(true);
  }

  function scheduleClose() {
    closeTimer.current = setTimeout(() => setOpen(false), 200);
  }

  function cancelClose() {
    if (closeTimer.current) clearTimeout(closeTimer.current);
  }

  // Close on route change.
  useEffect(() => {
    setOpen(false);
  }, [pathname]);

  // Escape returns focus to trigger.
  useEffect(() => {
    if (!open) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") {
        setOpen(false);
        triggerRef.current?.focus();
      }
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open]);

  // Focus trap inside panel.
  function onPanelKeyDown(e: React.KeyboardEvent<HTMLDivElement>) {
    if (e.key !== "Tab") return;
    const focusables = panelRef.current?.querySelectorAll<HTMLElement>(
      "a[href], button:not([disabled])",
    );
    const first = focusables?.[0];
    const last = focusables?.[focusables.length - 1];
    if (!first || !last) return;
    const active = document.activeElement;
    if (e.shiftKey && (active === first || active === triggerRef.current)) {
      e.preventDefault();
      last.focus();
    } else if (!e.shiftKey && active === last) {
      e.preventDefault();
      triggerRef.current?.focus();
    }
  }

  const employers = (
    query.data?.recommended_companies?.length
      ? query.data.recommended_companies
      : query.data?.spotlight_companies ?? []
  ).slice(0, 5);
  const strategicPartner =
    query.data?.spotlight_companies?.find((c) => c.is_verified) ?? null;
  const campaign = query.data?.sponsored_banner ?? null;

  return (
    <div className="relative h-full">
      <Link
        ref={triggerRef}
        href="/companies"
        onMouseEnter={openMenu}
        onMouseLeave={scheduleClose}
        onFocus={openMenu}
        aria-haspopup="true"
        aria-expanded={open}
        aria-current={isActive ? "page" : undefined}
        aria-controls="company-mega-menu"
        className={cn(
          "relative inline-flex shrink-0 items-center gap-1 whitespace-nowrap text-sm outline-none transition-colors",
          "focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/40",
          pill
            ? [
                "rounded-full px-4 py-2",
                open || isActive
                  ? "bg-[var(--brand-navy)]/10 font-semibold text-[var(--brand-navy)]"
                  : "text-[var(--text-secondary)] hover:bg-[var(--brand-navy)]/6 hover:text-[var(--brand-navy)]",
              ]
            : [
                "h-full px-0 font-semibold",
                "after:pointer-events-none after:absolute after:inset-x-0 after:bottom-0 after:h-[2px] after:origin-center after:rounded-full after:bg-[var(--brand-primary)] after:transition-transform after:duration-200",
                open || isActive
                  ? "text-[var(--brand-primary)] after:scale-x-100"
                  : "text-[var(--text-secondary)] after:scale-x-0 hover:text-[var(--brand-navy)] hover:after:scale-x-100",
              ],
          triggerClassName,
        )}
      >
        {tNav("companies")}
        <CaretDown
          aria-hidden
          weight="bold"
          className={cn(
            "size-3.5 transition-transform duration-200",
            open && "rotate-180",
          )}
        />
      </Link>

      {open && (
        <div
          ref={panelRef}
          id="company-mega-menu"
          role="region"
          aria-label={t("label")}
          onKeyDown={onPanelKeyDown}
          onMouseEnter={cancelClose}
          onMouseLeave={scheduleClose}
          className="fixed left-1/2 top-[68px] z-40 w-[min(calc(100vw-32px),1120px)] -translate-x-1/2"
        >
          {/* Invisible bridge fills the gap between trigger bottom and panel top,
              so the cursor doesn't trigger mouseleave while crossing it. */}
          <div className="h-2" />
          <div className="overflow-hidden rounded-[18px] border border-[var(--border-default)] bg-[var(--surface-card)] shadow-[0_18px_50px_rgba(11,34,57,0.13),0_4px_14px_rgba(11,34,57,0.05)]">
            <div className="grid gap-x-6 gap-y-5 p-5 md:grid-cols-[1.08fr_1fr_0.95fr]">
              {/* Column 1 — top employers */}
              <section aria-labelledby="mega-employers">
                <h3
                  id="mega-employers"
                  className="text-[11px] font-bold uppercase tracking-wide text-[var(--text-muted)]"
                >
                  {t("recommendedCompanies")}
                </h3>
                <ul className="mt-3 flex flex-col gap-0.5">
                  {query.isPending && hasOpened
                    ? Array.from({ length: 5 }).map((_, i) => (
                        <li key={i} className="flex items-center gap-2.5 px-2 py-1.5">
                          <Skeleton className="size-9 rounded-lg" />
                          <Skeleton className="h-4 w-32" />
                        </li>
                      ))
                    : employers.length > 0
                      ? employers.map((c) => (
                          <li key={c.id}>
                            <TrackedItem
                              surface="mega_companies"
                              targetType="company"
                              targetId={c.id}
                              renderId={`mega-company-${renderId}`}
                              signalTags={companySignalTags(c)}
                            >
                              <Link
                                href={`/companies/${c.slug}`}
                                className="group flex items-center gap-2.5 rounded-xl px-2.5 py-2 outline-none transition-colors hover:bg-[var(--surface-secondary)] focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/40"
                              >
                                <CompanyAvatar name={c.display_name} logoUrl={c.logo_url} size="sm" />
                                <span className="flex min-w-0 flex-1 items-center gap-1 truncate text-sm font-medium text-[var(--text-primary)]">
                                  <span className="truncate">{c.display_name}</span>
                                  {c.is_verified && (
                                    <VerifiedBadge label={tCompanies("verified")} className="[&_svg]:size-3.5" />
                                  )}
                                </span>
                                <CaretRight
                                  aria-hidden
                                  weight="bold"
                                  className="size-3.5 shrink-0 text-[var(--text-muted)] opacity-0 transition-opacity group-hover:opacity-100"
                                />
                              </Link>
                            </TrackedItem>
                          </li>
                        ))
                      : (
                        <li className="px-2 py-2 text-sm text-[var(--text-muted)]">
                          {t("emptyEmployers")}
                        </li>
                      )}
                </ul>
                <FooterLink href="/companies" label={t("viewAllCompanies")} />
              </section>

              {/* Column 2 — curated industries */}
              <section aria-labelledby="mega-industries">
                <h3
                  id="mega-industries"
                  className="text-[11px] font-bold uppercase tracking-wide text-[var(--text-muted)]"
                >
                  {t("industries")}
                </h3>
                <ul className="mt-3 flex flex-col gap-0.5">
                  {INDUSTRIES.map(({ key, query: industryQuery, icon: IndustryIcon }) => (
                    <li key={key}>
                      <Link
                        href={`/companies?industry=${encodeURIComponent(industryQuery)}`}
                        className="group flex items-center gap-2.5 rounded-xl px-2.5 py-2 text-sm font-medium text-[var(--text-secondary)] outline-none transition-colors hover:bg-[var(--surface-secondary)] hover:text-[var(--text-primary)] focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/40"
                      >
                        <IndustryIcon
                          aria-hidden
                          weight="duotone"
                          className="size-4 shrink-0 text-[var(--brand-primary)]"
                        />
                        <span className="truncate">{t(`industry.${key}`)}</span>
                      </Link>
                    </li>
                  ))}
                </ul>
                <FooterLink href="/companies" label={t("viewAllIndustries")} />
              </section>

              {/* Column 3 — strategic partner spotlight */}
              <section aria-labelledby="mega-partner">
                <h3
                  id="mega-partner"
                  className="text-[11px] font-bold uppercase tracking-wide text-[var(--text-muted)]"
                >
                  {t("strategicPartner")}
                </h3>
                {strategicPartner ? (
                  <TrackedItem
                    surface="mega_companies"
                    targetType="company"
                    targetId={strategicPartner.id}
                    renderId={`mega-company-spotlight-${renderId}`}
                    signalTags={companySignalTags(strategicPartner)}
                  >
                    <Link
                      href={`/companies/${strategicPartner.slug}`}
                      className="group mt-3 flex flex-col gap-2 rounded-2xl border border-[var(--border-default)] bg-[var(--surface-secondary)] p-4 outline-none transition-colors hover:border-[var(--brand-primary)]/60 hover:bg-[var(--surface-card)] focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]"
                    >
                      <span className="flex items-center gap-2.5">
                        <CompanyAvatar
                          name={strategicPartner.display_name}
                          logoUrl={strategicPartner.logo_url}
                          size="md"
                        />
                        <span className="flex min-w-0 flex-col">
                          <span className="flex items-center gap-1 text-sm font-bold text-[var(--text-primary)]">
                            <span className="truncate">{strategicPartner.display_name}</span>
                            <VerifiedBadge label={tCompanies("verified")} className="[&_svg]:size-3.5" />
                          </span>
                          <span className="text-xs font-semibold text-[var(--brand-teal)]">
                            {t("strategicPartner")}
                          </span>
                        </span>
                      </span>
                      {strategicPartner.industry && (
                        <span className="text-sm text-[var(--text-secondary)]">
                          {strategicPartner.industry}
                        </span>
                      )}
                      <span className="mt-auto inline-flex items-center gap-1 text-sm font-semibold text-[var(--brand-primary)]">
                        {t("learnMore")}
                        <ArrowRight aria-hidden weight="bold" className="size-3.5" />
                      </span>
                    </Link>
                  </TrackedItem>
                ) : (
                  <Link
                    href="/companies"
                    className="group mt-3 flex flex-col gap-2 rounded-xl border border-[var(--border-default)] bg-[var(--surface-secondary)] p-4 outline-none transition-colors hover:border-[var(--brand-primary)]/60 hover:bg-[var(--surface-card)] focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]"
                  >
                    <span className="flex size-10 items-center justify-center rounded-xl icon-chip-primary shadow-sm">
                      <Buildings aria-hidden weight="duotone" className="size-5 text-white" />
                    </span>
                    <span className="text-sm font-bold text-[var(--text-primary)]">
                      {t("verifiedTitle")}
                    </span>
                    <span className="text-sm text-[var(--text-secondary)]">
                      {t("partnerBlurb")}
                    </span>
                    <span className="mt-auto inline-flex items-center gap-1 text-sm font-semibold text-[var(--brand-primary)]">
                      {t("learnMore")}
                      <ArrowRight aria-hidden weight="bold" className="size-3.5" />
                    </span>
                  </Link>
                )}
                <MegaCampaignCard banner={campaign} className="mt-4" />
              </section>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function FooterLink({ href, label }: { href: string; label: string }) {
  return (
    <Link
      href={href}
      className="mt-3 inline-flex items-center gap-1 text-sm font-semibold text-[var(--brand-primary)] outline-none hover:underline focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/40"
    >
      {label}
      <ArrowRight aria-hidden weight="bold" className="size-3.5" />
    </Link>
  );
}
