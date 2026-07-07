"use client";

import { useState, useCallback } from "react";
import { useTranslations } from "next-intl";
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
  BarSeries,
} from "@/components/ui";
import {
  aiOpsApi,
  type AiOpsRange,
  type AiOpsSpendRow,
  type AiOpsVolumeRow,
} from "@/lib/api/ai-ops";
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
/* Metric tile                                                                */
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
  budget: number;
  unpricedLabel: string;
}) {
  const t = useTranslations("adminConsole.aiOps.spend");
  const tAiOps = useTranslations("adminConsole.aiOps");

  // Spend returns a bare list from api.get
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

  // Real rows: AiOpsSpendRow[] — bare list
  const rows: AiOpsSpendRow[] = query.data ?? [];
  // When group_by=feature, day is null and task_type is the group key.
  // Aggregate cost by task_type for the bar chart.
  const featureMap = new Map<string, number>();
  for (const row of rows) {
    const key = row.task_type ?? "unknown";
    featureMap.set(key, (featureMap.get(key) ?? 0) + (row.cost_usd ?? 0));
  }

  const barData: BarDataPoint[] = Array.from(featureMap.entries())
    .sort(([, a], [, b]) => b - a)
    .map(([label, val]) => ({
      label: label.slice(0, 12),
      value: Math.round(val * 10000) / 10000,
    }));

  const totalSpend = barData.reduce((s, d) => s + d.value, 0);
  const burnPct = budgetBurnPct(totalSpend, budget);

  const burndownNote =
    isFinite(budget) && budget > 0
      ? t("burndownLabel", {
          pct: burnPct,
          budget: budget.toFixed(2),
        })
      : null;

  // Show an unpriced note when rows have masked identity (provider/model null)
  // and non-zero cost — the admin should add a price row for those slots.
  const hasUnpriced = rows.some(
    (r) => r.provider === null && r.model === null && (r.cost_usd ?? 0) > 0,
  );

  return (
    <PanelCard title={t("panelTitle")} icon={CurrencyDollar}>
      {hasUnpriced && (
        <p className="mb-3">
          <UnpricedNote label={unpricedLabel} />
        </p>
      )}
      <BarSeries
        data={barData}
        referenceLine={isFinite(budget) && budget > 0 ? budget : undefined}
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
}: {
  range: AiOpsRange;
}) {
  const t = useTranslations("adminConsole.aiOps.reliability");
  const tAiOps = useTranslations("adminConsole.aiOps");

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

  const data = query.data;
  // circuit_states is an object map {key: state} — convert to array for table
  const circuitEntries = Object.entries(data.circuit_states ?? {});

  return (
    <PanelCard title={t("panelTitle")} icon={Gauge}>
      {/* Scalar aggregate metrics */}
      <div className="mb-5 grid grid-cols-2 gap-4 sm:grid-cols-4">
        <div className="flex flex-col gap-0.5">
          <span className="text-[0.6875rem] font-semibold uppercase tracking-wide text-[var(--text-muted)]">
            {t("requestsLabel")}
          </span>
          <span
            className="font-mono text-lg font-bold tabular-nums text-[var(--text-primary)]"
            style={{ fontFamily: "'JetBrains Mono', ui-monospace, monospace" }}
          >
            {new Intl.NumberFormat().format(data.requests)}
          </span>
        </div>
        <div className="flex flex-col gap-0.5">
          <span className="text-[0.6875rem] font-semibold uppercase tracking-wide text-[var(--text-muted)]">
            {t("errorRateLabel")}
          </span>
          <span
            className={cn(
              "font-mono text-lg font-bold tabular-nums",
              data.error_rate > 0.05
                ? "text-[var(--brand-red)]"
                : "text-[var(--text-primary)]",
            )}
            style={{ fontFamily: "'JetBrains Mono', ui-monospace, monospace" }}
          >
            {formatErrorRate(data.error_rate)}
          </span>
        </div>
        <div className="flex flex-col gap-0.5">
          <span className="text-[0.6875rem] font-semibold uppercase tracking-wide text-[var(--text-muted)]">
            {t("fallbackRateLabel")}
          </span>
          <span
            className="font-mono text-lg font-bold tabular-nums text-[var(--text-primary)]"
            style={{ fontFamily: "'JetBrains Mono', ui-monospace, monospace" }}
          >
            {formatErrorRate(data.fallback_rate)}
          </span>
        </div>
        <div className="flex flex-col gap-0.5">
          <span className="text-[0.6875rem] font-semibold uppercase tracking-wide text-[var(--text-muted)]">
            {t("fallbacksLabel")}
          </span>
          <span
            className="font-mono text-lg font-bold tabular-nums text-[var(--text-primary)]"
            style={{ fontFamily: "'JetBrains Mono', ui-monospace, monospace" }}
          >
            {new Intl.NumberFormat().format(data.fallbacks)}
          </span>
        </div>
      </div>

      {/* Circuit breaker states — object map converted to table rows */}
      <h3 className="mb-3 text-xs font-bold uppercase tracking-wide text-[var(--text-muted)]">
        {t("circuitStateTitle")}
      </h3>
      {circuitEntries.length === 0 ? (
        <p className="py-4 text-center text-sm text-[var(--text-muted)]">
          {t("noCircuits")}
        </p>
      ) : (
        <div className="overflow-x-auto rounded-xl border border-[var(--border-subtle)]">
          <table className="w-full border-collapse text-sm">
            <thead>
              <tr className="border-b border-[var(--border-subtle)] bg-[var(--bg-subtle)]">
                <th className="px-3.5 py-2 text-left text-[11px] font-semibold uppercase tracking-wide text-[var(--text-muted)]">
                  {t("circuitCol.alias")}
                </th>
                <th className="px-3.5 py-2 text-left text-[11px] font-semibold uppercase tracking-wide text-[var(--text-muted)]">
                  {t("circuitCol.state")}
                </th>
              </tr>
            </thead>
            <tbody>
              {circuitEntries.map(([key, state]) => (
                <tr
                  key={key}
                  className="border-b border-[var(--border-subtle)] last:border-0"
                >
                  <td className="px-3.5 py-2.5">
                    <span
                      className="font-mono text-xs font-semibold text-[var(--text-primary)]"
                      style={{ fontFamily: "'JetBrains Mono', ui-monospace, monospace" }}
                    >
                      {key}
                    </span>
                  </td>
                  <td className="px-3.5 py-2.5">
                    <span className="text-xs text-[var(--text-secondary)]">
                      {typeof state === "string" ? state : JSON.stringify(state)}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
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

  // Volume returns a bare list from api.get
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

  // Real rows: AiOpsVolumeRow[] — bare list, group_by=feature so day=null, task_type=group key
  const rows: AiOpsVolumeRow[] = query.data ?? [];

  // Aggregate by feature (task_type)
  const featureMap = new Map<string, { requests: number; tokens: number }>();
  for (const row of rows) {
    const key = row.task_type ?? "unknown";
    const prev = featureMap.get(key) ?? { requests: 0, tokens: 0 };
    featureMap.set(key, {
      requests: prev.requests + (row.requests ?? 0),
      tokens: prev.tokens + (row.prompt_tokens ?? 0) + (row.completion_tokens ?? 0),
    });
  }

  const featureEntries = Array.from(featureMap.entries()).sort(
    ([, a], [, b]) => b.requests - a.requests,
  );

  const barData: BarDataPoint[] = featureEntries.map(([group, val]) => ({
    label: group.slice(0, 8),
    value: val.requests,
  }));

  // Volume rows don't have provider/model — no unpriced concept here
  void unpricedLabel;

  return (
    <PanelCard title={t("panelTitle")} icon={StackSimple}>
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
    // spend_today and budget are numbers from the real backend
    const spendToday = data.spend_today ?? 0;
    const budget = data.budget ?? 0;
    const burn = budgetBurnPct(spendToday, budget);
    const tone = budgetTone(spendToday, budget);
    const statusTone = burnToneToStatusTone(tone);

    return (
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        {/* Spend today */}
        <MetricTile
          label={t("metric.spendToday")}
          value={formatUsd(spendToday)}
          icon={CurrencyDollar}
          tone={tone === "red" ? "danger" : tone === "amber" ? "warning" : "success"}
          badge={
            <StatusBadge tone={statusTone}>
              {burn}% {t("budgetBurn.ofBudget")}
            </StatusBadge>
          }
          sub={t("budgetBurn.budgetNote", {
            budget: budget.toFixed(2),
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

        {/* p95 latency — only field the backend returns for latency */}
        <MetricTile
          label={t("metric.p95Latency")}
          value={formatLatency(data.p95_latency_ms ?? NaN)}
          icon={Timer}
          tone="primary"
        />
      </div>
    );
  };

  const budgetVal = overviewQuery.data?.budget ?? 0;

  return (
    <div className="space-y-6">
      {renderTiles()}

      {/* Independent panels — each handles its own loading/error state */}
      <SpendPanel
        range={range}
        budget={budgetVal}
        unpricedLabel={unpricedLabel}
      />

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
        <ReliabilityPanel range={range} />
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
