"use client";

import { useState, useCallback } from "react";
import { useTranslations, useLocale } from "next-intl";
import { useQuery } from "@tanstack/react-query";
import {
  CurrencyDollar,
  LightningA,
  Warning,
  Timer,
  Gauge,
  StackSimple,
  WarningCircle,
} from "@phosphor-icons/react";
import { PageHeader } from "@/components/layout/page-header";
import {
  Tabs,
  TabPanel,
  SegmentedControl,
  StatusBadge,
  Skeleton,
  SkeletonCard,
  EmptyState,
  DataTable,
  BarSeries,
} from "@/components/ui";
import type { Column } from "@/components/ui";
import {
  aiOpsApi,
  type AiOpsRange,
  type AiOpsCircuitState,
  type AiOpsReliabilityRow,
} from "@/lib/api/ai-ops";
import { formatDateTime } from "@/lib/format";
import {
  budgetTone,
  budgetBurnPct,
  formatUsd,
  formatLatency,
  formatErrorRate,
} from "./ai-ops-helpers";
import { cn } from "@/lib/utils";
import type { BarDataPoint } from "@/components/ui/bar-series";
import { AiTracesScreen } from "./ai-traces-screen";
import { AiPricingScreen } from "./ai-pricing-screen";
import { AiSettingsTab } from "./ai-settings-tab";

/* -------------------------------------------------------------------------- */
/* Visibility-gated refetch interval helper                                   */
/* -------------------------------------------------------------------------- */

const REFETCH_INTERVAL = 45_000;

function visibilityGatedInterval(interval: number) {
  return () =>
    typeof document !== "undefined" &&
    document.visibilityState === "visible"
      ? interval
      : false;
}

/* -------------------------------------------------------------------------- */
/* Budget burn badge                                                          */
/* -------------------------------------------------------------------------- */

import type { StatusTone } from "@/components/ui";

function burnToneToStatusTone(tone: "teal" | "amber" | "red"): StatusTone {
  if (tone === "teal") return "active";
  if (tone === "amber") return "pending";
  return "rejected";
}

/* -------------------------------------------------------------------------- */
/* Unpriced note                                                               */
/* -------------------------------------------------------------------------- */

function UnpricedNote({ label }: { label: string }) {
  return (
    <span className="inline-flex items-center gap-1 rounded border border-[var(--amber-400)]/40 bg-[var(--amber-50)] px-1.5 py-0.5 text-[0.65rem] font-semibold text-[var(--amber-700)]">
      <Warning aria-hidden weight="fill" className="size-3 shrink-0" />
      {label}
    </span>
  );
}

/* -------------------------------------------------------------------------- */
/* Panel wrapper                                                              */
/* -------------------------------------------------------------------------- */

function PanelCard({
  title,
  icon: Icon,
  children,
  className,
}: {
  title: string;
  icon: React.ElementType;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <section
      aria-labelledby={`panel-${title.toLowerCase().replace(/\s+/g, "-")}`}
      className={cn("marketplace-card rounded-[12px] p-5", className)}
    >
      <h2
        id={`panel-${title.toLowerCase().replace(/\s+/g, "-")}`}
        className="mb-4 flex items-center gap-2 text-sm font-bold tracking-tight text-[var(--text-primary)]"
      >
        <span className="icon-chip-primary flex size-7 shrink-0 items-center justify-center rounded-lg shadow-sm">
          <Icon aria-hidden weight="duotone" className="size-4" />
        </span>
        {title}
      </h2>
      {children}
    </section>
  );
}

/* -------------------------------------------------------------------------- */
/* Metric tile (custom — richer than MetricTiles for spend-specific display) */
/* -------------------------------------------------------------------------- */

function MetricTile({
  label,
  value,
  sub,
  icon: Icon,
  tone = "primary",
  badge,
}: {
  label: string;
  value: string;
  sub?: string;
  icon: React.ElementType;
  tone?: "primary" | "warning" | "danger" | "success";
  badge?: React.ReactNode;
}) {
  const chipClass =
    tone === "warning"
      ? "icon-chip-warning"
      : tone === "danger"
        ? "icon-chip-danger"
        : tone === "success"
          ? "icon-chip-success"
          : "icon-chip-primary";

  return (
    <div className="marketplace-card flex flex-col rounded-[12px] px-4 py-3.5">
      <div className="flex items-start justify-between gap-2">
        <span className="truncate text-[0.8125rem] font-medium text-[var(--text-secondary)]">
          {label}
        </span>
        <span
          className={cn(
            "flex size-7 shrink-0 items-center justify-center rounded-lg",
            chipClass,
          )}
        >
          <Icon aria-hidden weight="duotone" className="size-4" />
        </span>
      </div>
      <span
        className="mt-1.5 font-mono text-[1.75rem] font-bold leading-none tracking-tight tabular-nums text-[var(--text-primary)]"
        style={{ fontFamily: "'JetBrains Mono', ui-monospace, monospace" }}
      >
        {value}
      </span>
      {(sub ?? badge) && (
        <div className="mt-1.5 flex items-center gap-2">
          {badge}
          {sub && (
            <span className="truncate text-[0.6875rem] font-medium text-[var(--text-muted)]">
              {sub}
            </span>
          )}
        </div>
      )}
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* Spend panel                                                                 */
/* -------------------------------------------------------------------------- */

function SpendPanel({
  range,
  budget,
  unpricedLabel,
}: {
  range: AiOpsRange;
  budget: string;
  unpricedLabel: string;
}) {
  const t = useTranslations("adminConsole.aiOps.spend");
  const tAiOps = useTranslations("adminConsole.aiOps");
  const locale = useLocale();

  const query = useQuery({
    queryKey: ["ai-ops", "spend", range] as const,
    queryFn: () => aiOpsApi.spend(range, "feature"),
    staleTime: 30_000,
    refetchInterval: visibilityGatedInterval(REFETCH_INTERVAL),
    retry: 1,
  });

  if (query.isPending) {
    return (
      <PanelCard title={t("panelTitle")} icon={CurrencyDollar}>
        <Skeleton className="h-32 w-full" />
      </PanelCard>
    );
  }

  if (query.isError) {
    return (
      <PanelCard title={t("panelTitle")} icon={CurrencyDollar}>
        <EmptyState
          kind="error"
          icon={WarningCircle}
          title={t("errorTitle")}
          description={t("errorBody")}
          action={
            <button
              onClick={() => void query.refetch()}
              className="text-xs font-semibold text-[var(--brand-primary)] underline-offset-2 hover:underline"
            >
              {tAiOps("retry")}
            </button>
          }
        />
      </PanelCard>
    );
  }

  const rows = query.data?.rows ?? [];
  const hasUnpriced = rows.some(
    (r) => r.provider === null || r.model === null,
  );

  // Aggregate daily spend: group by date (ts prefix)
  const dailyMap = new Map<string, number>();
  for (const row of rows) {
    const day = row.ts.slice(0, 10); // ISO date prefix
    const prev = dailyMap.get(day) ?? 0;
    dailyMap.set(day, prev + parseFloat(row.cost_usd));
  }

  const barData: BarDataPoint[] = Array.from(dailyMap.entries())
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([day, val]) => ({
      label: new Intl.DateTimeFormat(locale === "vi" ? "vi-VN" : "en-US", {
        month: "short",
        day: "numeric",
      }).format(new Date(day)),
      value: Math.round(val * 10000) / 10000,
    }));

  const budgetNum = parseFloat(budget);
  const totalSpend = barData.reduce((s, d) => s + d.value, 0);
  const burnPct = budgetBurnPct(totalSpend, budgetNum);

  const burndownNote =
    isFinite(budgetNum) && budgetNum > 0
      ? t("burndownLabel", {
          pct: burnPct,
          budget: budgetNum.toFixed(2),
        })
      : null;

  return (
    <PanelCard title={t("panelTitle")} icon={CurrencyDollar}>
      {hasUnpriced && (
        <p className="mb-3">
          <UnpricedNote label={unpricedLabel} />
        </p>
      )}
      <BarSeries
        data={barData}
        referenceLine={isFinite(budgetNum) ? budgetNum : undefined}
        format={(v) => formatUsd(v)}
        emptyLabel={t("emptyLabel")}
        ariaLabel={t("ariaLabel")}
        className="mb-2"
      />
      {burndownNote && (
        <p className="mt-2 text-[0.6875rem] text-[var(--text-muted)]">
          {burndownNote}
        </p>
      )}
    </PanelCard>
  );
}

/* -------------------------------------------------------------------------- */
/* Reliability panel                                                           */
/* -------------------------------------------------------------------------- */

function ReliabilityPanel({
  range,
  unpricedLabel,
}: {
  range: AiOpsRange;
  unpricedLabel: string;
}) {
  const t = useTranslations("adminConsole.aiOps.reliability");
  const tAiOps = useTranslations("adminConsole.aiOps");
  const locale = useLocale();

  const query = useQuery({
    queryKey: ["ai-ops", "reliability", range] as const,
    queryFn: () => aiOpsApi.reliability(range, "feature"),
    staleTime: 30_000,
    refetchInterval: visibilityGatedInterval(REFETCH_INTERVAL),
    retry: 1,
  });

  if (query.isPending) {
    return (
      <PanelCard title={t("panelTitle")} icon={Gauge}>
        <Skeleton className="h-32 w-full" />
      </PanelCard>
    );
  }

  if (query.isError) {
    return (
      <PanelCard title={t("panelTitle")} icon={Gauge}>
        <EmptyState
          kind="error"
          icon={WarningCircle}
          title={t("errorTitle")}
          description={t("errorBody")}
          action={
            <button
              onClick={() => void query.refetch()}
              className="text-xs font-semibold text-[var(--brand-primary)] underline-offset-2 hover:underline"
            >
              {tAiOps("retry")}
            </button>
          }
        />
      </PanelCard>
    );
  }

  const rows = query.data?.rows ?? [];
  const circuits = query.data?.circuit_states ?? [];
  const hasUnpriced = rows.some(
    (r) => r.provider === null || r.model === null,
  );

  // Circuit state tone
  function circuitTone(
    state: AiOpsCircuitState["state"],
  ): "active" | "rejected" | "pending" {
    if (state === "closed") return "active";
    if (state === "open") return "rejected";
    return "pending";
  }

  const circuitColumns: Column<AiOpsCircuitState>[] = [
    {
      key: "alias",
      header: t("circuitCol.alias"),
      cell: (row) => (
        <span className="font-mono text-xs font-semibold text-[var(--text-primary)]">
          {row.alias}
        </span>
      ),
    },
    {
      key: "state",
      header: t("circuitCol.state"),
      cell: (row) => (
        <StatusBadge tone={circuitTone(row.state)}>
          {t(`circuitState.${row.state}`)}
        </StatusBadge>
      ),
    },
    {
      key: "failures",
      header: t("circuitCol.failures"),
      align: "right",
      cell: (row) => (
        <span
          className="font-mono text-xs tabular-nums"
          style={{ fontFamily: "'JetBrains Mono', ui-monospace, monospace" }}
        >
          {row.failures}
        </span>
      ),
    },
    {
      key: "last_failure_at",
      header: t("circuitCol.lastFailure"),
      cell: (row) => (
        <span className="text-xs text-[var(--text-muted)]">
          {row.last_failure_at
            ? formatDateTime(row.last_failure_at, locale)
            : "—"}
        </span>
      ),
    },
  ];

  return (
    <PanelCard title={t("panelTitle")} icon={Gauge}>
      {hasUnpriced && (
        <p className="mb-3">
          <UnpricedNote label={unpricedLabel} />
        </p>
      )}

      {/* Per-feature reliability metrics */}
      {rows.length > 0 ? (
        <div className="mb-5 overflow-x-auto">
          <table className="w-full border-collapse text-sm">
            <thead>
              <tr className="border-b border-[var(--border-subtle)]">
                <th className="pb-2 pr-4 text-left text-[11px] font-semibold uppercase tracking-wide text-[var(--text-muted)]">
                  {t("featureCol")}
                </th>
                <th className="pb-2 pr-4 text-right text-[11px] font-semibold uppercase tracking-wide text-[var(--text-muted)]">
                  {t("errorRateLabel")}
                </th>
                <th className="pb-2 pr-4 text-right text-[11px] font-semibold uppercase tracking-wide text-[var(--text-muted)]">
                  {t("fallbackRateLabel")}
                </th>
                <th className="pb-2 pr-4 text-right text-[11px] font-semibold uppercase tracking-wide text-[var(--text-muted)]">
                  {t("p50Label")}
                </th>
                <th className="pb-2 text-right text-[11px] font-semibold uppercase tracking-wide text-[var(--text-muted)]">
                  {t("p95Label")}
                </th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row: AiOpsReliabilityRow) => (
                <tr
                  key={row.group}
                  className="border-b border-[var(--border-subtle)] last:border-0"
                >
                  <td className="py-2 pr-4">
                    <div className="flex flex-col gap-0.5">
                      <span className="text-xs font-semibold text-[var(--text-primary)]">
                        {row.group}
                      </span>
                      {(row.provider === null || row.model === null) && (
                        <UnpricedNote label={unpricedLabel} />
                      )}
                    </div>
                  </td>
                  <td className="py-2 pr-4 text-right">
                    <span
                      className={cn(
                        "font-mono text-xs tabular-nums",
                        row.error_rate > 0.05
                          ? "font-bold text-[var(--brand-red)]"
                          : "text-[var(--text-primary)]",
                      )}
                      style={{
                        fontFamily: "'JetBrains Mono', ui-monospace, monospace",
                      }}
                    >
                      {formatErrorRate(row.error_rate)}
                    </span>
                  </td>
                  <td className="py-2 pr-4 text-right">
                    <span
                      className="font-mono text-xs tabular-nums text-[var(--text-secondary)]"
                      style={{
                        fontFamily: "'JetBrains Mono', ui-monospace, monospace",
                      }}
                    >
                      {formatErrorRate(row.fallback_rate)}
                    </span>
                  </td>
                  <td className="py-2 pr-4 text-right">
                    <span
                      className="font-mono text-xs tabular-nums text-[var(--text-secondary)]"
                      style={{
                        fontFamily: "'JetBrains Mono', ui-monospace, monospace",
                      }}
                    >
                      {formatLatency(row.p50_ms)}
                    </span>
                  </td>
                  <td className="py-2 text-right">
                    <span
                      className="font-mono text-xs tabular-nums text-[var(--text-secondary)]"
                      style={{
                        fontFamily: "'JetBrains Mono', ui-monospace, monospace",
                      }}
                    >
                      {formatLatency(row.p95_ms)}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <EmptyState
          kind="empty"
          title={t("emptyLabel")}
          className="mb-4 py-6"
        />
      )}

      {/* Circuit breaker states */}
      <h3 className="mb-3 text-xs font-bold uppercase tracking-wide text-[var(--text-muted)]">
        {t("circuitStateTitle")}
      </h3>
      <DataTable
        columns={circuitColumns}
        rows={circuits}
        getRowId={(r) => r.alias}
        empty={{
          kind: "empty",
          title: t("noCircuits"),
        }}
        caption={t("circuitStateTitle")}
      />
    </PanelCard>
  );
}

/* -------------------------------------------------------------------------- */
/* Volume panel                                                                */
/* -------------------------------------------------------------------------- */

function VolumePanel({
  range,
  unpricedLabel,
}: {
  range: AiOpsRange;
  unpricedLabel: string;
}) {
  const t = useTranslations("adminConsole.aiOps.volume");
  const tAiOps = useTranslations("adminConsole.aiOps");

  const query = useQuery({
    queryKey: ["ai-ops", "volume", range] as const,
    queryFn: () => aiOpsApi.volume(range, "feature"),
    staleTime: 30_000,
    refetchInterval: visibilityGatedInterval(REFETCH_INTERVAL),
    retry: 1,
  });

  if (query.isPending) {
    return (
      <PanelCard title={t("panelTitle")} icon={StackSimple}>
        <Skeleton className="h-32 w-full" />
      </PanelCard>
    );
  }

  if (query.isError) {
    return (
      <PanelCard title={t("panelTitle")} icon={StackSimple}>
        <EmptyState
          kind="error"
          icon={WarningCircle}
          title={t("errorTitle")}
          description={t("errorBody")}
          action={
            <button
              onClick={() => void query.refetch()}
              className="text-xs font-semibold text-[var(--brand-primary)] underline-offset-2 hover:underline"
            >
              {tAiOps("retry")}
            </button>
          }
        />
      </PanelCard>
    );
  }

  const rows = query.data?.rows ?? [];
  const hasUnpriced = rows.some(
    (r) => r.provider === null || r.model === null,
  );

  // Aggregate by feature
  const featureMap = new Map<string, { requests: number; tokens: number }>();
  for (const row of rows) {
    const prev = featureMap.get(row.group) ?? { requests: 0, tokens: 0 };
    featureMap.set(row.group, {
      requests: prev.requests + row.requests,
      tokens:
        prev.tokens + row.prompt_tokens + row.completion_tokens,
    });
  }

  const featureEntries = Array.from(featureMap.entries()).sort(
    ([, a], [, b]) => b.requests - a.requests,
  );

  const barData: BarDataPoint[] = featureEntries.map(([group, val]) => ({
    label: group.slice(0, 8), // truncate long feature slugs in axis
    value: val.requests,
  }));

  return (
    <PanelCard title={t("panelTitle")} icon={StackSimple}>
      {hasUnpriced && (
        <p className="mb-3">
          <UnpricedNote label={unpricedLabel} />
        </p>
      )}

      {/* By-feature bar chart */}
      <h3 className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-[var(--text-muted)]">
        {t("byFeatureTitle")}
      </h3>
      <BarSeries
        data={barData}
        format={(v) => new Intl.NumberFormat().format(v)}
        emptyLabel={t("emptyLabel")}
        ariaLabel={t("ariaLabel")}
        className="mb-5"
      />

      {/* Top consumers list */}
      {featureEntries.length > 0 && (
        <>
          <h3 className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-[var(--text-muted)]">
            {t("topConsumersTitle")}
          </h3>
          {(() => {
              const totalRequests = featureEntries.reduce(
                (s, [, v]) => s + v.requests,
                0,
              );
              return (
                <ul className="space-y-1.5" role="list">
                  {featureEntries.slice(0, 8).map(([group, val]: [string, { requests: number; tokens: number }]) => {
                    const pct =
                      totalRequests > 0
                        ? Math.round((val.requests / totalRequests) * 100)
                        : 0;

                    return (
                      <li
                        key={group}
                        className="flex items-center justify-between gap-3 text-xs"
                      >
                        <div className="flex min-w-0 flex-1 flex-col gap-0.5">
                          <span className="truncate font-semibold text-[var(--text-primary)]">
                            {group}
                          </span>
                          <div className="h-1.5 w-full overflow-hidden rounded-full bg-[var(--bg-muted)]">
                            <div
                              className="h-full rounded-full bg-[var(--gray-400)]"
                              style={{ width: `${Math.max(pct, 2)}%` }}
                              role="meter"
                              aria-valuenow={pct}
                              aria-valuemin={0}
                              aria-valuemax={100}
                              aria-label={`${group}: ${pct}%`}
                            />
                          </div>
                        </div>
                        <div className="flex shrink-0 flex-col items-end gap-0.5">
                          <span
                            className="font-mono font-semibold tabular-nums text-[var(--text-primary)]"
                            style={{
                              fontFamily: "'JetBrains Mono', ui-monospace, monospace",
                            }}
                          >
                            {new Intl.NumberFormat().format(val.requests)}
                          </span>
                          <span className="text-[0.65rem] text-[var(--text-muted)]">
                            {pct}%
                          </span>
                        </div>
                      </li>
                    );
                  })}
                </ul>
              );
            })()}

        </>
      )}
    </PanelCard>
  );
}

/* -------------------------------------------------------------------------- */
/* Overview tab (metric tiles + panels)                                       */
/* -------------------------------------------------------------------------- */

function OverviewTab({ range }: { range: AiOpsRange }) {
  const t = useTranslations("adminConsole.aiOps");
  const locale = useLocale();

  const overviewQuery = useQuery({
    queryKey: ["ai-ops", "overview", range] as const,
    queryFn: () => aiOpsApi.overview(range),
    staleTime: 30_000,
    refetchInterval: visibilityGatedInterval(REFETCH_INTERVAL),
    retry: 1,
  });

  const unpricedLabel = t("unpriced");

  // Metric tiles
  const renderTiles = () => {
    if (overviewQuery.isPending) {
      return (
        <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <SkeletonCard key={i} />
          ))}
        </div>
      );
    }

    if (overviewQuery.isError) {
      return (
        <EmptyState
          kind="error"
          icon={WarningCircle}
          title={t("spend.errorTitle")}
          description={t("spend.errorBody")}
          action={
            <button
              onClick={() => void overviewQuery.refetch()}
              className="text-xs font-semibold text-[var(--brand-primary)] underline-offset-2 hover:underline"
            >
              {t("retry")}
            </button>
          }
        />
      );
    }

    const data = overviewQuery.data;
    const burn = budgetBurnPct(data.spend_today, data.budget);
    const tone = budgetTone(data.spend_today, data.budget);
    const statusTone = burnToneToStatusTone(tone);

    return (
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        {/* Spend today */}
        <MetricTile
          label={t("metric.spendToday")}
          value={formatUsd(data.spend_today)}
          icon={CurrencyDollar}
          tone={tone === "red" ? "danger" : tone === "amber" ? "warning" : "success"}
          badge={
            <StatusBadge tone={statusTone}>
              {burn}% {t("budgetBurn.ofBudget")}
            </StatusBadge>
          }
          sub={t("budgetBurn.budgetNote", {
            budget: parseFloat(data.budget).toFixed(2),
          })}
        />

        {/* Requests */}
        <MetricTile
          label={t("metric.requests")}
          value={new Intl.NumberFormat().format(data.requests)}
          icon={LightningA}
          tone="primary"
        />

        {/* Error rate */}
        <MetricTile
          label={t("metric.errorRate")}
          value={formatErrorRate(data.error_rate)}
          icon={Warning}
          tone={data.error_rate > 0.05 ? "danger" : data.error_rate > 0.01 ? "warning" : "success"}
        />

        {/* p95 latency */}
        <MetricTile
          label={t("metric.p95Latency")}
          value={formatLatency(data.p95_latency_ms ?? NaN)}
          icon={Timer}
          tone="primary"
          sub={
            data.updated_at
              ? t("updated", {
                  time: formatDateTime(data.updated_at, locale),
                })
              : undefined
          }
        />
      </div>
    );
  };

  return (
    <div className="space-y-6">
      {renderTiles()}

      {/* Independent panels — each handles its own loading/error state */}
      <SpendPanel
        range={range}
        budget={overviewQuery.data?.budget ?? "0"}
        unpricedLabel={unpricedLabel}
      />

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
        <ReliabilityPanel range={range} unpricedLabel={unpricedLabel} />
        <VolumePanel range={range} unpricedLabel={unpricedLabel} />
      </div>
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* Main screen                                                                */
/* -------------------------------------------------------------------------- */

const TAB_ID_BASE = "ai-ops";

export function AiOperationsOverviewScreen() {
  const t = useTranslations("adminConsole.aiOps");

  const [activeTab, setActiveTab] = useState("overview");
  const [range, setRange] = useState<AiOpsRange>("today");

  const handleRangeChange = useCallback(
    (v: string) => setRange(v as AiOpsRange),
    [],
  );

  const tabItems = [
    { value: "overview", label: t("tabs.overview") },
    { value: "traces", label: t("tabs.traces") },
    { value: "models-pricing", label: t("tabs.modelsPricing") },
    { value: "settings", label: t("tabs.settings") },
  ];

  const rangeOptions = [
    { value: "today", label: t("range.today") },
    { value: "7d", label: t("range.7d") },
    { value: "30d", label: t("range.30d") },
  ];

  return (
    <>
      <PageHeader
        title={t("pageTitle")}
        actions={
          <SegmentedControl
            value={range}
            onValueChange={handleRangeChange}
            options={rangeOptions}
            ariaLabel={t("range.label")}
            size="sm"
          />
        }
      />

      <Tabs
        items={tabItems}
        value={activeTab}
        onValueChange={setActiveTab}
        ariaLabel={t("pageTitle")}
        idBase={TAB_ID_BASE}
      />

      <TabPanel tabsId={TAB_ID_BASE} value="overview" active={activeTab === "overview"}>
        <OverviewTab range={range} />
      </TabPanel>

      <TabPanel tabsId={TAB_ID_BASE} value="traces" active={activeTab === "traces"}>
        <AiTracesScreen range={range} />
      </TabPanel>

      <TabPanel tabsId={TAB_ID_BASE} value="models-pricing" active={activeTab === "models-pricing"}>
        <AiPricingScreen />
      </TabPanel>

      <TabPanel tabsId={TAB_ID_BASE} value="settings" active={activeTab === "settings"}>
        <AiSettingsTab />
      </TabPanel>
    </>
  );
}
