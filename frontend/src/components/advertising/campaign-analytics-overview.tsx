"use client";

import { useLocale, useTranslations } from "next-intl";
import { useQuery } from "@tanstack/react-query";
import {
  ChartBar,
  Eye,
  CursorClick,
  PaperPlaneTilt,
  WarningCircle,
  type Icon,
} from "@phosphor-icons/react";
import { Button, Skeleton } from "@/components/ui";
import { advertisingApi } from "@/lib/api";
import {
  formatCount,
  formatRatePct,
  isOrgAnalyticsEmpty,
} from "@/lib/advertising/analytics";

/**
 * Org-wide campaign analytics rollup for the partner workspace (spec §7).
 * AGGREGATES-ONLY: total impressions / clicks / CTR / apply-starts and a small
 * per-campaign list. Never an individual viewer / PII. Rendered only when the
 * org already has campaigns (the main screen handles the zero-campaign empty
 * state), and self-heals its own loading / error / no-signal states.
 */
export function CampaignAnalyticsOverview({
  titles,
}: {
  /** placement_id → target title, resolved from the loaded placement rows. */
  titles: Record<string, string>;
}) {
  const t = useTranslations("advertising");
  const tc = useTranslations("common");
  const locale = useLocale();

  const query = useQuery({
    queryKey: ["advertising", "analytics", "org"],
    queryFn: () => advertisingApi.getOrgAnalytics(),
    retry: false,
  });

  const data = query.data;

  return (
    <section
      className="mb-5 rounded-2xl border border-[var(--border-default)] bg-white px-4 py-4 shadow-[0_2px_12px_rgba(11,34,57,0.06)]"
      aria-labelledby="org-analytics-heading"
    >
      <div className="mb-3 flex items-start gap-2.5">
        <span className="flex size-8 shrink-0 items-center justify-center rounded-xl icon-chip-neutral shadow-sm">
          <ChartBar aria-hidden weight="duotone" className="size-4 text-white" />
        </span>
        <div className="min-w-0">
          <h2
            id="org-analytics-heading"
            className="text-sm font-bold text-[var(--text-primary)]"
          >
            {t("orgAnalytics.title")}
          </h2>
          <p className="mt-0.5 text-xs text-[var(--text-secondary)]">
            {t("orgAnalytics.subtitle")}
          </p>
        </div>
      </div>

      {query.isPending ? (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4" aria-hidden>
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-[62px] rounded-xl" />
          ))}
        </div>
      ) : query.isError ? (
        <div
          role="alert"
          className="flex flex-wrap items-center gap-3 rounded-xl border border-[var(--red-400)]/40 bg-[var(--red-50)] px-3.5 py-3 text-sm text-[var(--text-secondary)]"
        >
          <WarningCircle
            aria-hidden
            weight="duotone"
            className="size-4 text-[var(--brand-red)]"
          />
          <span>{t("orgAnalytics.errorBody")}</span>
          <Button variant="ghost" size="sm" onClick={() => query.refetch()}>
            {tc("retry")}
          </Button>
        </div>
      ) : isOrgAnalyticsEmpty(data) ? (
        <p className="rounded-xl border border-dashed border-[var(--border-default)] px-3.5 py-4 text-center text-sm text-[var(--text-muted)]">
          {t("orgAnalytics.emptyBody")}
        </p>
      ) : (
        data && (
          <>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              <Kpi
                icon={Eye}
                label={t("analytics.kpi.impressions")}
                value={formatCount(data.totals.impressions, locale)}
              />
              <Kpi
                icon={CursorClick}
                label={t("analytics.kpi.clicks")}
                value={formatCount(data.totals.clicks, locale)}
              />
              <Kpi
                label={t("analytics.kpi.ctr")}
                value={formatRatePct(data.ctr_pct)}
              />
              <Kpi
                icon={PaperPlaneTilt}
                label={t("analytics.kpi.applyStarts")}
                value={formatCount(data.totals.apply_starts, locale)}
              />
            </div>

            {data.campaigns.length > 0 && (
              <div className="mt-3.5">
                <p className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-[var(--text-muted)]">
                  {t("orgAnalytics.byCampaign")}
                </p>
                <ul className="divide-y divide-[var(--border-default)] rounded-xl border border-[var(--border-default)]">
                  {data.campaigns.slice(0, 5).map((c) => (
                    <li
                      key={c.placement_id}
                      className="flex items-center justify-between gap-3 px-3.5 py-2.5"
                    >
                      <span className="min-w-0 truncate text-sm font-medium text-[var(--text-primary)]">
                        {titles[c.placement_id] ?? t("orgAnalytics.campaignFallback")}
                      </span>
                      <span className="flex shrink-0 items-center gap-3 text-xs text-[var(--text-secondary)]">
                        <span className="tabular-nums">
                          {t("orgAnalytics.impressionsShort", {
                            count: formatCount(c.impressions, locale),
                          })}
                        </span>
                        <span className="tabular-nums font-semibold text-[var(--text-primary)]">
                          {t("orgAnalytics.ctrShort", {
                            value: formatRatePct(c.ctr_pct),
                          })}
                        </span>
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            <p className="mt-3 text-xs text-[var(--text-muted)]">{data.note}</p>
          </>
        )
      )}
    </section>
  );
}

function Kpi({
  icon: IconCmp,
  label,
  value,
}: {
  icon?: Icon;
  label: string;
  value: string;
}) {
  return (
    <div className="rounded-xl border border-[var(--border-default)] bg-[var(--bg-subtle)] px-3 py-2.5">
      <div className="flex items-center gap-1.5 text-[var(--text-muted)]">
        {IconCmp && <IconCmp aria-hidden weight="duotone" className="size-3.5" />}
        <span className="text-[11px] font-medium">{label}</span>
      </div>
      <p className="mt-0.5 text-lg font-black tracking-tight text-[var(--text-primary)]">
        {value}
      </p>
    </div>
  );
}
