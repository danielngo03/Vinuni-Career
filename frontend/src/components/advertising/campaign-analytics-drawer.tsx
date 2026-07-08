"use client";

import { useLocale, useTranslations } from "next-intl";
import { useQuery } from "@tanstack/react-query";
import {
  ChartLineUp,
  Eye,
  CursorClick,
  PaperPlaneTilt,
  ShieldWarning,
  WarningCircle,
  Info,
  type Icon,
} from "@phosphor-icons/react";
import {
  Button,
  EmptyState,
  Sheet,
  Skeleton,
  Sparkline,
  StatusBadge,
} from "@/components/ui";
import { advertisingApi, type Placement } from "@/lib/api";
import {
  analyticsErrorKind,
  formatCount,
  formatRatePct,
  impressionsSeries,
  isPlacementAnalyticsEmpty,
} from "@/lib/advertising/analytics";
import { formatVnd } from "@/lib/advertising/format";
import { PLACEMENT_TYPE_TONE, useAdvertisingLabels } from "@/lib/advertising/labels";

/**
 * Per-campaign analytics drawer (spec §7). Owner-scoped, AGGREGATES-ONLY:
 * totals, CTR, apply-start rate, cost per apply-start (the partner's OWN spend),
 * and a daily series. NEVER an individual viewer / PII. A cross-org / unknown
 * placement resolves to 404 → a clean not-authorized state (we never confirm the
 * placement exists).
 */
export function CampaignAnalyticsDrawer({
  open,
  onClose,
  placement,
}: {
  open: boolean;
  onClose: () => void;
  placement: Placement | null;
}) {
  const t = useTranslations("advertising");
  const tc = useTranslations("common");
  const locale = useLocale();
  const labels = useAdvertisingLabels();

  const query = useQuery({
    queryKey: ["advertising", "analytics", "placement", placement?.id],
    queryFn: () => advertisingApi.getPlacementAnalytics(placement!.id),
    enabled: open && placement != null,
    retry: false,
  });

  const analytics = query.data;

  return (
    <Sheet
      open={open && placement != null}
      onClose={onClose}
      title={t("analytics.drawerTitle")}
      size="lg"
      closeLabel={tc("close")}
    >
      {placement && (
        <div className="space-y-5">
          {/* Campaign identity. */}
          <div className="flex flex-wrap items-center gap-2">
            <StatusBadge tone={PLACEMENT_TYPE_TONE[placement.placement_type] ?? "info"}>
              {labels.placementType(
                placement.placement_type,
                placement.placement_type_label,
              )}
            </StatusBadge>
            <span className="min-w-0 truncate text-sm font-semibold text-[var(--text-primary)]">
              {placement.target_title ?? t("targetUnavailable")}
            </span>
          </div>

          {query.isPending ? (
            <AnalyticsSkeleton />
          ) : query.isError ? (
            analyticsErrorKind(query.error) === "notAuthorized" ? (
              <EmptyState
                kind="permission"
                icon={ShieldWarning}
                title={t("analytics.notAuthorizedTitle")}
                description={t("analytics.notAuthorizedBody")}
              />
            ) : (
              <EmptyState
                kind="error"
                icon={WarningCircle}
                title={t("analytics.errorTitle")}
                description={t("analytics.errorBody")}
                action={
                  <Button variant="secondary" onClick={() => query.refetch()}>
                    {tc("retry")}
                  </Button>
                }
              />
            )
          ) : isPlacementAnalyticsEmpty(analytics) ? (
            <EmptyState
              kind="empty"
              icon={ChartLineUp}
              title={t("analytics.emptyTitle")}
              description={t("analytics.emptyBody")}
            />
          ) : (
            analytics && (
              <>
                {/* KPI grid. */}
                <div className="grid grid-cols-2 gap-3">
                  <Kpi
                    icon={Eye}
                    label={t("analytics.kpi.impressions")}
                    value={formatCount(analytics.totals.impressions, locale)}
                  />
                  <Kpi
                    icon={CursorClick}
                    label={t("analytics.kpi.clicks")}
                    value={formatCount(analytics.totals.clicks, locale)}
                  />
                  <Kpi
                    label={t("analytics.kpi.ctr")}
                    value={formatRatePct(analytics.ctr_pct)}
                  />
                  <Kpi
                    icon={PaperPlaneTilt}
                    label={t("analytics.kpi.applyStarts")}
                    value={formatCount(analytics.totals.apply_starts, locale)}
                  />
                  <Kpi
                    label={t("analytics.kpi.applyStartRate")}
                    value={formatRatePct(analytics.apply_start_rate_pct)}
                  />
                  <Kpi
                    label={t("analytics.kpi.costPerApplyStart")}
                    value={
                      analytics.cost_per_apply_start
                        ? formatVnd(
                            analytics.cost_per_apply_start,
                            analytics.currency,
                            locale,
                          )
                        : "—"
                    }
                  />
                </div>

                {/* Impressions trend. */}
                {analytics.daily.length > 1 && (
                  <div className="rounded-xl border border-[var(--border-default)] bg-white px-3.5 py-3">
                    <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-[var(--text-muted)]">
                      {t("analytics.trendTitle")}
                    </p>
                    <Sparkline
                      data={impressionsSeries(analytics)}
                      ariaLabel={t("analytics.trendAria")}
                      className="h-10"
                    />
                  </div>
                )}

                {/* Daily breakdown table. */}
                <div className="rounded-xl border border-[var(--border-default)] bg-white">
                  <p className="border-b border-[var(--border-default)] px-3.5 py-2.5 text-xs font-semibold uppercase tracking-wide text-[var(--text-muted)]">
                    {t("analytics.tableTitle")}
                  </p>
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <caption className="sr-only">
                        {t("analytics.tableTitle")}
                      </caption>
                      <thead>
                        <tr className="text-left text-[11px] font-semibold uppercase tracking-wide text-[var(--text-muted)]">
                          <th scope="col" className="px-3.5 py-2">
                            {t("analytics.col.date")}
                          </th>
                          <th scope="col" className="px-2 py-2 text-right">
                            {t("analytics.col.impressions")}
                          </th>
                          <th scope="col" className="px-2 py-2 text-right">
                            {t("analytics.col.clicks")}
                          </th>
                          <th scope="col" className="px-2 py-2 text-right">
                            {t("analytics.col.ctr")}
                          </th>
                          <th scope="col" className="px-3.5 py-2 text-right">
                            {t("analytics.col.applyStarts")}
                          </th>
                        </tr>
                      </thead>
                      <tbody>
                        {analytics.daily.map((d) => (
                          <tr
                            key={d.date}
                            className="border-t border-[var(--border-default)] text-[var(--text-secondary)]"
                          >
                            <th
                              scope="row"
                              className="whitespace-nowrap px-3.5 py-2 text-left font-medium text-[var(--text-primary)]"
                            >
                              {d.date}
                            </th>
                            <td className="px-2 py-2 text-right tabular-nums">
                              {formatCount(d.impressions, locale)}
                            </td>
                            <td className="px-2 py-2 text-right tabular-nums">
                              {formatCount(d.clicks, locale)}
                            </td>
                            <td className="px-2 py-2 text-right tabular-nums">
                              {formatRatePct(d.ctr_pct)}
                            </td>
                            <td className="px-3.5 py-2 text-right tabular-nums">
                              {formatCount(d.apply_starts, locale)}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>

                {/* Aggregates-only disclosure (backend-localized). */}
                <p className="flex items-start gap-2 text-xs text-[var(--text-muted)]">
                  <Info aria-hidden weight="duotone" className="mt-0.5 size-3.5 shrink-0" />
                  <span>{analytics.note}</span>
                </p>
              </>
            )
          )}
        </div>
      )}
    </Sheet>
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
    <div className="rounded-xl border border-[var(--border-default)] bg-white px-3.5 py-3">
      <div className="flex items-center gap-1.5 text-[var(--text-muted)]">
        {IconCmp && <IconCmp aria-hidden weight="duotone" className="size-3.5" />}
        <span className="text-[11px] font-medium">{label}</span>
      </div>
      <p className="mt-1 text-xl font-black tracking-tight text-[var(--text-primary)]">
        {value}
      </p>
    </div>
  );
}

function AnalyticsSkeleton() {
  return (
    <div className="space-y-4" aria-hidden>
      <div className="grid grid-cols-2 gap-3">
        {Array.from({ length: 6 }).map((_, i) => (
          <Skeleton key={i} className="h-[68px] rounded-xl" />
        ))}
      </div>
      <Skeleton className="h-16 rounded-xl" />
      <Skeleton className="h-40 rounded-xl" />
    </div>
  );
}
