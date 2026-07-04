"use client";

import { useTranslations } from "next-intl";
import { Crown, Files, WarningCircle } from "@phosphor-icons/react";
import { Link } from "@/i18n/navigation";
import type { CvLibraryMeta } from "@/lib/api";

/**
 * When an active subscription overrides the default student tier, the library
 * quota source flips to "subscription" and `active_cv_limit` reflects the paid
 * tier (e.g. 10). Show the plan context + a link to manage the subscription.
 */
export function QuotaStrip({ meta }: { meta: CvLibraryMeta | null }) {
  const t = useTranslations("cv");
  if (!meta) return null;

  const isSubscriptionQuota = meta.quota_source === "subscription";

  return (
    <div className="mb-5 flex flex-wrap items-center gap-x-4 gap-y-1.5">
      <span
        className="inline-flex items-center gap-1.5 rounded-full border border-[var(--border-default)] bg-[var(--surface-card)] px-3 py-1 text-sm font-semibold text-[var(--text-secondary)] shadow-sm"
        aria-label={
          isSubscriptionQuota
            ? t("quota.counterSub", {
                used: meta.active_cv_used,
                limit: meta.active_cv_limit,
              })
            : t("quota.counter", {
                used: meta.active_cv_used,
                limit: meta.active_cv_limit,
              })
        }
      >
        <Files
          aria-hidden
          weight="duotone"
          className="size-4 text-[var(--brand-primary)]"
        />
        {t("quota.counter", {
          used: meta.active_cv_used,
          limit: meta.active_cv_limit,
        })}
        {isSubscriptionQuota && (
          <span
            aria-hidden
            className="inline-flex items-center gap-1 rounded-full bg-[var(--brand-primary)]/10 px-2 py-0.5 text-xs font-semibold text-[var(--brand-primary)]"
          >
            <Crown weight="duotone" className="size-3.5" />
            {t("quota.planBadge")}
          </span>
        )}
      </span>
      {isSubscriptionQuota && (
        <Link
          href="/student/billing"
          className="text-sm font-semibold text-[var(--brand-primary)] underline-offset-2 outline-none hover:underline focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/40"
        >
          {t("quota.managePlan")}
        </Link>
      )}
      {!meta.can_create && (
        <span className="inline-flex items-center gap-1.5 text-sm font-medium text-[var(--amber-700)]">
          <WarningCircle aria-hidden weight="fill" className="size-4" />
          {t("quota.disabledHint", { limit: meta.active_cv_limit })}
        </span>
      )}
    </div>
  );
}
