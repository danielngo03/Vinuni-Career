"use client";

import { useTranslations } from "next-intl";
import { MapPin, Briefcase, Users } from "@phosphor-icons/react";
import { Link } from "@/i18n/navigation";
import { StarDisplay } from "@/components/reviews/star-rating";
import { VerifiedBadge } from "@/components/ui/verified-badge";
import { CompanyAvatar } from "./company-avatar";
import type { CompanySummary } from "@/lib/api";

/**
 * Public partner card for the directory grid and homepage spotlight. Verified
 * badge is shown only when the backend reports `is_verified`. Stable height for
 * a clean grid; the whole card links to the partner detail page.
 */
export function CompanyCard({ company }: { company: CompanySummary }) {
  const t = useTranslations("companies");

  return (
    <Link
      href={`/companies/${company.slug}`}
      className="marketplace-card marketplace-card-hover group flex h-full min-h-[150px] flex-col rounded-[14px] p-5 outline-none focus-visible:border-[var(--brand-primary)] focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/30"
    >
      <div className="flex items-start gap-3">
        <CompanyAvatar
          name={company.display_name}
          logoUrl={company.logo_url}
          size="md"
        />
        <div className="min-w-0 flex-1">
          <h3 className="flex items-center gap-1 text-base font-bold tracking-tight text-[var(--text-primary)] group-hover:text-[var(--brand-primary)]">
            <span className="truncate">{company.display_name}</span>
            {company.is_verified && (
              <VerifiedBadge label={t("verified")} />
            )}
          </h3>
          {company.industry && (
            <p className="mt-0.5 truncate text-sm text-[var(--text-secondary)]">
              {company.industry}
            </p>
          )}
        </div>
      </div>

      <dl className="mt-3 flex flex-1 flex-col gap-1.5 text-sm text-[var(--text-secondary)]">
        {company.headquarters_city && (
          <div className="flex items-center gap-2">
            <MapPin
              aria-hidden
              weight="duotone"
              className="size-4 shrink-0 text-[var(--text-muted)]"
            />
            <dt className="sr-only">{t("hq")}</dt>
            <dd className="truncate">{company.headquarters_city}</dd>
          </div>
        )}
        {company.company_size && (
          <div className="flex items-center gap-2">
            <Users
              aria-hidden
              weight="duotone"
              className="size-4 shrink-0 text-[var(--text-muted)]"
            />
            <dt className="sr-only">{t("companySize")}</dt>
            <dd className="truncate">{t("companySizeLabel", { size: company.company_size })}</dd>
          </div>
        )}
        <div className="flex items-center gap-2">
          <Briefcase
            aria-hidden
            weight="duotone"
            className="size-4 shrink-0 text-[var(--text-muted)]"
          />
          <dt className="sr-only">{t("openRoles")}</dt>
          <dd className="font-medium text-[var(--text-primary)]">
            {t("openRolesCount", { count: company.active_job_count })}
          </dd>
        </div>
        {company.rating && company.rating.overall_avg != null && (
          <div className="flex items-center gap-1.5">
            <StarDisplay value={company.rating.overall_avg} size={13} />
            <span className="font-data text-xs tabular-nums text-[var(--text-muted)]">
              {company.rating.overall_avg.toFixed(1)}
              <span className="ml-1 text-[11px]">
                ({t("reviewCount", { count: company.rating.review_count })})
              </span>
            </span>
          </div>
        )}
      </dl>
    </Link>
  );
}
