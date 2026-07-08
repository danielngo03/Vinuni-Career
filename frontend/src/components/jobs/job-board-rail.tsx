"use client";

import Image from "next/image";
import { useTranslations } from "next-intl";
import { useQuery } from "@tanstack/react-query";
import {
  Buildings,
  ShieldCheck,
  Sparkle,
  GraduationCap,
  ArrowRight,
} from "@phosphor-icons/react";
import { Link } from "@/i18n/navigation";
import { Skeleton } from "@/components/ui";
import { companiesApi, type CompanySummary } from "@/lib/api";

function CompanyAvatar({ company }: { company: CompanySummary }) {
  if (company.logo_url) {
    return (
      <Image
        src={company.logo_url}
        alt=""
        aria-hidden
        width={36}
        height={36}
        className="size-9 shrink-0 rounded-lg object-cover"
      />
    );
  }
  const initials = company.display_name
    .split(/\s+/)
    .slice(0, 2)
    .map((w) => w[0]?.toUpperCase() ?? "")
    .join("");
  const hue = (company.display_name.charCodeAt(0) * 47) % 360;
  return (
    <div
      className="size-9 shrink-0 rounded-lg bg-gradient-to-br from-[var(--brand-primary)]/60 to-[var(--ai-accent)]/60 flex items-center justify-center text-white text-xs font-bold"
      style={{ background: `hsl(${hue},50%,50%)` }}
      aria-hidden
    >
      {initials || <Buildings className="size-4" />}
    </div>
  );
}

function FeaturedCompanies() {
  const t = useTranslations("jobs.rail");

  const query = useQuery({
    queryKey: ["companies", "rail-featured"],
    queryFn: () => companiesApi.list({ limit: 5 }),
    staleTime: 5 * 60 * 1000,
    retry: false,
  });

  if (query.isPending) {
    return (
      <div className="space-y-3 py-1">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="flex items-center gap-2.5">
            <Skeleton className="size-9 shrink-0 rounded-lg" />
            <div className="flex-1 space-y-1.5">
              <Skeleton className="h-3.5 w-3/4" />
              <Skeleton className="h-3 w-1/2" />
            </div>
          </div>
        ))}
      </div>
    );
  }

  const companies = query.data?.data ?? [];
  if (companies.length === 0) return null;

  return (
    <ul className="space-y-3">
      {companies.map((company) => (
        <li key={company.id}>
          <Link
            href={`/companies/${company.slug}`}
            className="grid grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-2.5 rounded-xl p-2 transition-colors hover:bg-[var(--surface-secondary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/30"
          >
            <CompanyAvatar company={company} />
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-1">
                <p className="truncate text-sm font-semibold text-[var(--text-primary)]">
                  {company.display_name}
                </p>
                {company.is_verified && (
                  <ShieldCheck
                    weight="fill"
                    className="size-3.5 shrink-0 text-[var(--ai-accent)]"
                    aria-label={t("verifiedLabel")}
                  />
                )}
              </div>
              <p className="text-xs text-[var(--text-muted)]">
                {company.active_job_count > 0
                  ? t("openRoles", { count: company.active_job_count })
                  : (company.industry ?? t("noOpenRoles"))}
              </p>
            </div>
            <ArrowRight className="size-3.5 shrink-0 text-[var(--text-muted)]" aria-hidden />
          </Link>
        </li>
      ))}
    </ul>
  );
}

export function JobBoardRail() {
  const t = useTranslations("jobs.rail");

  return (
    <aside className="hidden lg:flex lg:flex-col lg:gap-4" aria-label={t("ariaLabel")}>
      {/* Featured employers */}
      <div className="marketplace-card overflow-hidden rounded-[18px]">
        <div className="flex items-center justify-between border-b border-[var(--border-default)] px-4 py-3">
          <div className="flex items-center gap-2">
            <span className="flex size-7 shrink-0 items-center justify-center rounded-xl icon-chip-primary shadow-sm">
              <Buildings weight="duotone" className="size-3.5 text-white" aria-hidden />
            </span>
            <h2 className="text-sm font-bold text-[var(--text-primary)]">
              {t("featuredTitle")}
            </h2>
          </div>
          <Link
            href="/companies"
            className="inline-flex items-center gap-0.5 text-xs font-semibold text-[var(--brand-primary)] hover:underline focus-visible:outline-none"
          >
            {t("viewAll")}
            <ArrowRight className="size-3" aria-hidden />
          </Link>
        </div>
        <div className="p-2">
          <FeaturedCompanies />
        </div>
      </div>

      {/* VinUni curated badge */}
      <div className="marketplace-card overflow-hidden rounded-[18px]">
        <div className="relative h-28 overflow-hidden">
          <Image
            src="/images/vinuni-campus.png"
            alt=""
            fill
            sizes="320px"
            className="object-cover"
          />
          <div className="absolute inset-0 bg-gradient-to-t from-[var(--brand-navy)]/80 via-[var(--brand-navy)]/20 to-transparent" />
          <span className="absolute left-4 top-4 inline-flex items-center gap-1.5 rounded-full bg-[var(--glass-surface-heavy)] px-3 py-1 text-[10px] font-bold uppercase tracking-widest text-[var(--brand-primary)] shadow-sm">
            <GraduationCap weight="duotone" className="size-3.5" aria-hidden />
            {t("curatedBadge")}
          </span>
        </div>
        <div className="p-4">
          <p className="text-sm leading-relaxed text-[var(--text-secondary)]">
            {t("curatedBody")}
          </p>
          <Link
            href="/companies"
            className="mt-3 inline-flex items-center gap-1 text-sm font-semibold text-[var(--brand-primary)] hover:underline focus-visible:outline-none"
          >
            {t("curatedCta")}
            <ArrowRight className="size-3.5" aria-hidden />
          </Link>
        </div>
      </div>

      {/* AI quick tip */}
      <div className="marketplace-card rounded-[18px] p-4">
        <div className="mb-2.5 flex items-center gap-2">
          <span className="flex size-7 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-[var(--teal-500)] to-[var(--brand-primary)] shadow-sm">
            <Sparkle weight="duotone" className="size-3.5 text-white" aria-hidden />
          </span>
          <span className="text-sm font-bold text-[var(--text-primary)]">
            {t("aiTipTitle")}
          </span>
        </div>
        <p className="text-sm leading-relaxed text-[var(--text-secondary)]">
          {t("aiTipBody")}
        </p>
      </div>
    </aside>
  );
}
