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
  GridFour,
  DotsNine,
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
} from "@/components/ui";
import {
  TimeSeriesChart,
  StackedBarChart,
  DonutChart,
  Heatmap,
} from "@/components/ui/charts";
import type { TimeSeriesDataPoint, StackedBarDataPoint, DonutSlice, HeatmapCell } from "@/components/ui/charts";
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
  id: panelId,
  title,
  icon: Icon,
  children,
  className,
}: {
  id: string;
  title: string;
  icon: React.ElementType;
  children: React.ReactNode;
  className?: string;
}) {
  const headingId = `aiops-panel-${panelId}`;
  return (
    <section
      aria-labelledby={headingId}
      className={cn("marketplace-card rounded-[12px] p-5", className)}
    >
      <h2
        id={headingId}
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
/* Range → integer mapping (mirrors aiOpsApi internal)                        */
/* -------------------------------------------------------------------------- */

function rangeToDays(range: AiOpsRange): number {
  if (range === "today") return 1;
  if (range === "7d") return 7;
  return 30;
}

/* -------------------------------------------------------------------------- */
/* Spend vs Budget panel (TimeSeriesChart area + reference line)              */
/* -------------------------------------------------------------------------- */

function SpendBudgetPanel({
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

  const rangeDays = rangeToDays(range);

  const tsQuery = useQuery({
    queryKey: ["ai-ops", "timeseries", rangeDays] as const,
    queryFn: () => aiOpsApi.timeseries(rangeDays),
    staleTime: 30_000,
    refetchInterval: visibilityGatedInterval(REFETCH_INTERVAL),
    retry: 1,
  });

  // Keep the spend-by-feature donut still using the spend endpoint
  const spendQuery = useQuery({
    queryKey: ["ai-ops", "spend", range] as const,
    queryFn: () => aiOpsApi.spend(range, "feature"),
    staleTime: 30_000,
    refetchInterval: visibilityGatedInterval(REFETCH_INTERVAL),
    retry: 1,
  });

  if (tsQuery.isPending) {
    return (
      <PanelCard id="spend" title={t("panelTitle")} icon={CurrencyDollar}>
        <Skeleton className="h-48 w-full" />
      </PanelCard>
    );
  }

  if (tsQuery.isError) {
    return (
      <PanelCard id="spend" title={t("panelTitle")} icon={CurrencyDollar}>
        <EmptyState
          kind="error"
          icon={WarningCircle}
          title={t("errorTitle")}
          description={t("errorBody")}
          action={
            <button
              onClick={() => void tsQuery.refetch()}
              className="text-xs font-semibold text-[var(--brand-primary)] underline-offset-2 hover:underline"
            >
              {tAiOps("retry")}
            </button>
          }
        />
      </PanelCard>
    );
  }

  const rows = tsQuery.data?.series ?? [];

  // Derive per-day budget for reference line:
  // budget from overview is the total configured budget.
  // If range = today (1 day), referenceValue = budget.
  // For multi-day ranges we show the daily budget as a reference line.
  const dailyBudget = isFinite(budget) && budget > 0 ? budget : undefined;

  const tsData: TimeSeriesDataPoint[] = rows.map((r) => ({
    day: r.day.slice(5), // "MM-DD" for display brevity
    cost_usd: r.cost_usd,
  }));

  // Check for unpriced rows in spend data
  const spendRows: AiOpsSpendRow[] = spendQuery.data ?? [];
  const hasUnpriced = spendRows.some(
    (r) => r.provider === null && r.model === null && (r.cost_usd ?? 0) > 0,
  );

  const totalSpend = rows.reduce((s, r) => s + r.cost_usd, 0);
  const burnPct = dailyBudget ? budgetBurnPct(totalSpend, dailyBudget * rangeDays) : 0;

  return (
    <PanelCard id="spend" title={t("panelTitle")} icon={CurrencyDollar}>
      {hasUnpriced && (
        <p className="mb-3">
          <UnpricedNote label={unpricedLabel} />
        </p>
      )}
      <TimeSeriesChart
        data={tsData}
        xKey="day"
        series={[{ key: "cost_usd", label: tAiOps("metric.spendToday"), type: "area" }]}
        format="currency"
        referenceValue={dailyBudget}
        height={220}
        ariaLabel={t("ariaLabel")}
        emptyLabel={t("emptyLabel")}
      />
      {dailyBudget && rangeDays > 1 && (
        <p className="mt-2 text-[0.6875rem] text-[var(--text-muted)]">
          {t("burndownLabel", { pct: burnPct, budget: (dailyBudget * rangeDays).toFixed(2) })}
        </p>
      )}
    </PanelCard>
  );
}

/* -------------------------------------------------------------------------- */
/* Latency panel (two-series TimeSeriesChart: avg + p95)                      */
/* -------------------------------------------------------------------------- */

function LatencyPanel({ range }: { range: AiOpsRange }) {
  const t = useTranslations("adminConsole.aiOps.latency");
  const tAiOps = useTranslations("adminConsole.aiOps");

  const rangeDays = rangeToDays(range);

  const query = useQuery({
    queryKey: ["ai-ops", "timeseries", rangeDays] as const,
    queryFn: () => aiOpsApi.timeseries(rangeDays),
    staleTime: 30_000,
    refetchInterval: visibilityGatedInterval(REFETCH_INTERVAL),
    retry: 1,
  });

  if (query.isPending) {
    return (
      <PanelCard id="latency" title={t("panelTitle")} icon={Timer}>
        <Skeleton className="h-48 w-full" />
      </PanelCard>
    );
  }

  if (query.isError) {
    return (
      <PanelCard id="latency" title={t("panelTitle")} icon={Timer}>
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

  const rows = query.data?.series ?? [];

  // Filter to only rows that have any latency data
  const hasAnyLatency = rows.some((r) => r.avg_latency_ms !== null || r.p95_latency_ms !== null);

  const tsData: TimeSeriesDataPoint[] = rows.map((r) => ({
    day: r.day.slice(5),
    // Replace null with undefined so recharts skips the null points (no crash)
    avg_latency_ms: r.avg_latency_ms ?? undefined,
    p95_latency_ms: r.p95_latency_ms ?? undefined,
  }));

  return (
    <PanelCard id="latency" title={t("panelTitle")} icon={Timer}>
      {!hasAnyLatency && rows.length > 0 ? (
        <div
          className="flex h-[220px] items-center justify-center rounded-lg border border-dashed border-[var(--border-default)] text-xs text-[var(--text-muted)]"
        >
          {t("emptyLabel")}
        </div>
      ) : (
        <TimeSeriesChart
          data={tsData}
          xKey="day"
          series={[
            { key: "p95_latency_ms", label: t("seriesP95"), type: "line" },
            { key: "avg_latency_ms", label: t("seriesAvg"), color: "#a3a3a3", type: "line" },
          ]}
          format="ms"
          height={220}
          ariaLabel={t("ariaLabel")}
          emptyLabel={t("emptyLabel")}
        />
      )}
    </PanelCard>
  );
}

/* -------------------------------------------------------------------------- */
/* Volume panel (StackedBarChart by feature per day)                          */
/* -------------------------------------------------------------------------- */

function VolumePanel({ range }: { range: AiOpsRange }) {
  const t = useTranslations("adminConsole.aiOps.volume");
  const tAiOps = useTranslations("adminConsole.aiOps");

  const rangeDays = rangeToDays(range);

  // For per-day breakdowns, use timeseries (requests) for the line view,
  // and volume grouped by feature for the stacked perspective
  const tsQuery = useQuery({
    queryKey: ["ai-ops", "timeseries", rangeDays] as const,
    queryFn: () => aiOpsApi.timeseries(rangeDays),
    staleTime: 30_000,
    refetchInterval: visibilityGatedInterval(REFETCH_INTERVAL),
    retry: 1,
  });

  const volumeQuery = useQuery({
    queryKey: ["ai-ops", "volume", range] as const,
    queryFn: () => aiOpsApi.volume(range, "feature"),
    staleTime: 30_000,
    refetchInterval: visibilityGatedInterval(REFETCH_INTERVAL),
    retry: 1,
  });

  if (tsQuery.isPending || volumeQuery.isPending) {
    return (
      <PanelCard id="volume" title={t("panelTitle")} icon={StackSimple}>
        <Skeleton className="h-48 w-full" />
      </PanelCard>
    );
  }

  if (tsQuery.isError) {
    return (
      <PanelCard id="volume" title={t("panelTitle")} icon={StackSimple}>
        <EmptyState
          kind="error"
          icon={WarningCircle}
          title={t("errorTitle")}
          description={t("errorBody")}
          action={
            <button
              onClick={() => void tsQuery.refetch()}
              className="text-xs font-semibold text-[var(--brand-primary)] underline-offset-2 hover:underline"
            >
              {tAiOps("retry")}
            </button>
          }
        />
      </PanelCard>
    );
  }

  const tsRows = tsQuery.data?.series ?? [];
  const volRows: AiOpsVolumeRow[] = volumeQuery.data ?? [];

  // Build stacked bar: pivot feature×day (feature from volume grouped rows)
  // volume group_by=feature has day=null, task_type = feature key
  // Since volume endpoint doesn't give us per-day per-feature breakdown,
  // we fall back to daily totals from timeseries as a single-series stacked bar
  const tsData: StackedBarDataPoint[] = tsRows.map((r) => ({
    day: r.day.slice(5),
    requests: r.requests,
  }));

  // Get feature breakdown for legend from volume grouped rows
  const featureMap = new Map<string, number>();
  for (const row of volRows) {
    const key = row.task_type ?? "unknown";
    featureMap.set(key, (featureMap.get(key) ?? 0) + row.requests);
  }

  return (
    <PanelCard id="volume" title={t("panelTitle")} icon={StackSimple}>
      <StackedBarChart
        data={tsData}
        xKey="day"
        series={[{ key: "requests", label: t("requestsLabel") }]}
        format="number"
        height={220}
        ariaLabel={t("ariaLabel")}
        emptyLabel={t("emptyLabel")}
      />

      {/* Top features list */}
      {featureMap.size > 0 && (
        <>
          <h3 className="mb-2 mt-4 text-[11px] font-semibold uppercase tracking-wide text-[var(--text-muted)]">
            {t("topConsumersTitle")}
          </h3>
          {(() => {
            const entries = Array.from(featureMap.entries()).sort(([, a], [, b]) => b - a);
            const total = entries.reduce((s, [, v]) => s + v, 0);
            return (
              <ul className="space-y-1.5" role="list">
                {entries.slice(0, 6).map(([group, count]) => {
                  const pct = total > 0 ? Math.round((count / total) * 100) : 0;
                  return (
                    <li key={group} className="flex items-center justify-between gap-3 text-xs">
                      <div className="flex min-w-0 flex-1 flex-col gap-0.5">
                        <span className="truncate font-semibold text-[var(--text-primary)]">{group}</span>
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
                          style={{ fontFamily: "'JetBrains Mono', ui-monospace, monospace" }}
                        >
                          {new Intl.NumberFormat().format(count)}
                        </span>
                        <span className="text-[0.65rem] text-[var(--text-muted)]">{pct}%</span>
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
/* Distribution panel (DonutChart spend/requests by feature)                  */
/* -------------------------------------------------------------------------- */

function DistributionPanel({ range }: { range: AiOpsRange }) {
  const t = useTranslations("adminConsole.aiOps.distribution");
  const tAiOps = useTranslations("adminConsole.aiOps");

  const query = useQuery({
    queryKey: ["ai-ops", "spend", range] as const,
    queryFn: () => aiOpsApi.spend(range, "feature"),
    staleTime: 30_000,
    refetchInterval: visibilityGatedInterval(REFETCH_INTERVAL),
    retry: 1,
  });

  if (query.isPending) {
    return (
      <PanelCard id="distribution" title={t("panelTitle")} icon={DotsNine}>
        <Skeleton className="h-48 w-full" />
      </PanelCard>
    );
  }

  if (query.isError) {
    return (
      <PanelCard id="distribution" title={t("panelTitle")} icon={DotsNine}>
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

  const rows: AiOpsSpendRow[] = query.data ?? [];

  // Aggregate spend by feature (task_type). model=null → group label "—" (restricted).
  const featureMap = new Map<string, number>();
  for (const row of rows) {
    const key = row.task_type ?? "—";
    featureMap.set(key, (featureMap.get(key) ?? 0) + row.cost_usd);
  }

  const slices: DonutSlice[] = Array.from(featureMap.entries())
    .filter(([, v]) => v > 0)
    .sort(([, a], [, b]) => b - a)
    .map(([label, value]) => ({ label: label.slice(0, 16), value }));

  return (
    <PanelCard id="distribution" title={t("panelTitle")} icon={DotsNine}>
      <DonutChart
        data={slices}
        height={240}
        ariaLabel={t("ariaLabel")}
        emptyLabel={t("emptyLabel")}
      />
    </PanelCard>
  );
}

/* -------------------------------------------------------------------------- */
/* Reliability panel (error-rate scalar + circuit states + error series)       */
/* -------------------------------------------------------------------------- */

function ReliabilityPanel({ range }: { range: AiOpsRange }) {
  const t = useTranslations("adminConsole.aiOps.reliability");
  const tAiOps = useTranslations("adminConsole.aiOps");

  const reliabilityQuery = useQuery({
    queryKey: ["ai-ops", "reliability", range] as const,
    queryFn: () => aiOpsApi.reliability(range, "feature"),
    staleTime: 30_000,
    refetchInterval: visibilityGatedInterval(REFETCH_INTERVAL),
    retry: 1,
  });

  const rangeDays = rangeToDays(range);
  const tsQuery = useQuery({
    queryKey: ["ai-ops", "timeseries", rangeDays] as const,
    queryFn: () => aiOpsApi.timeseries(rangeDays),
    staleTime: 30_000,
    refetchInterval: visibilityGatedInterval(REFETCH_INTERVAL),
    retry: 1,
  });

  if (reliabilityQuery.isPending) {
    return (
      <PanelCard id="reliability" title={t("panelTitle")} icon={Gauge}>
        <Skeleton className="h-48 w-full" />
      </PanelCard>
    );
  }

  if (reliabilityQuery.isError) {
    return (
      <PanelCard id="reliability" title={t("panelTitle")} icon={Gauge}>
        <EmptyState
          kind="error"
          icon={WarningCircle}
          title={t("errorTitle")}
          description={t("errorBody")}
          action={
            <button
              onClick={() => void reliabilityQuery.refetch()}
              className="text-xs font-semibold text-[var(--brand-primary)] underline-offset-2 hover:underline"
            >
              {tAiOps("retry")}
            </button>
          }
        />
      </PanelCard>
    );
  }

  const data = reliabilityQuery.data;
  const circuitEntries = Object.entries(data.circuit_states ?? {});

  // Build error rate series from timeseries if available
  const tsRows = tsQuery.data?.series ?? [];
  const errorTsData: TimeSeriesDataPoint[] = tsRows.map((r) => ({
    day: r.day.slice(5),
    error_rate: Number.isFinite(r.error_rate) ? r.error_rate * 100 : 0,
  }));
  const hasErrorSeries = errorTsData.length > 0 && tsRows.some((r) => r.errors > 0);

  return (
    <PanelCard id="reliability" title={t("panelTitle")} icon={Gauge}>
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

      {/* Error rate trend (small) */}
      {hasErrorSeries && (
        <div className="mb-5">
          <h3 className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-[var(--text-muted)]">
            {t("errorTrendTitle")}
          </h3>
          <TimeSeriesChart
            data={errorTsData}
            xKey="day"
            series={[{ key: "error_rate", label: t("errorRateLabel"), type: "area" }]}
            format="percent"
            height={140}
            ariaLabel={t("errorTrendTitle")}
            emptyLabel={t("emptyLabel")}
          />
        </div>
      )}

      {/* Circuit breaker states */}
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
/* Error heatmap panel (day × hour)                                           */
/* -------------------------------------------------------------------------- */

function ErrorHeatmapPanel({ range }: { range: AiOpsRange }) {
  const t = useTranslations("adminConsole.aiOps.errorHeatmap");
  const tAiOps = useTranslations("adminConsole.aiOps");

  const rangeDays = rangeToDays(range);

  const query = useQuery({
    queryKey: ["ai-ops", "error-heatmap", rangeDays] as const,
    queryFn: () => aiOpsApi.errorHeatmap(rangeDays),
    staleTime: 30_000,
    refetchInterval: visibilityGatedInterval(REFETCH_INTERVAL),
    retry: 1,
  });

  if (query.isPending) {
    return (
      <PanelCard id="errorHeatmap" title={t("panelTitle")} icon={GridFour}>
        <Skeleton className="h-48 w-full" />
      </PanelCard>
    );
  }

  if (query.isError) {
    return (
      <PanelCard id="errorHeatmap" title={t("panelTitle")} icon={GridFour}>
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

  const rawCells = query.data?.cells ?? [];

  // xLabels = hours 0-23 as strings; yLabels = unique days (ascending)
  const xLabels: string[] = Array.from({ length: 24 }, (_, i) => String(i));
  const daySet = new Set<string>();
  for (const c of rawCells) daySet.add(c.day);
  const yLabels: string[] = Array.from(daySet).sort().map((d) => d.slice(5)); // "MM-DD"

  const cells: HeatmapCell[] = rawCells.map((c) => ({
    x: String(c.hour),
    y: c.day.slice(5),
    value: c.errors,
  }));

  const heatmapHeight = Math.max(160, Math.min(yLabels.length * 22 + 32, 320));

  return (
    <PanelCard id="errorHeatmap" title={t("panelTitle")} icon={GridFour}>
      <Heatmap
        cells={cells}
        xLabels={xLabels}
        yLabels={yLabels}
        height={heatmapHeight}
        colorScale="severity"
        ariaLabel={t("ariaLabel")}
        emptyLabel={t("emptyLabel")}
      />
      <p className="mt-2 text-[0.6875rem] text-[var(--text-muted)]">{t("note")}</p>
    </PanelCard>
  );
}

/* -------------------------------------------------------------------------- */
/* Overview tab (metric tiles + all panels)                                   */
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
    const spendToday = data.spend_today ?? 0;
    const budget = data.budget ?? 0;
    const burn = budgetBurnPct(spendToday, budget);
    const tone = budgetTone(spendToday, budget);
    const statusTone = burnToneToStatusTone(tone);

    return (
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
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
          sub={t("budgetBurn.budgetNote", { budget: budget.toFixed(2) })}
        />
        <MetricTile
          label={t("metric.requests")}
          value={new Intl.NumberFormat().format(data.requests)}
          icon={LightningA}
          tone="primary"
        />
        <MetricTile
          label={t("metric.errorRate")}
          value={formatErrorRate(data.error_rate)}
          icon={Warning}
          tone={data.error_rate > 0.05 ? "danger" : data.error_rate > 0.01 ? "warning" : "success"}
        />
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

      {/* Spend vs Budget — full width */}
      <SpendBudgetPanel
        range={range}
        budget={budgetVal}
        unpricedLabel={unpricedLabel}
      />

      {/* Latency + Volume — two column */}
      <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
        <LatencyPanel range={range} />
        <VolumePanel range={range} />
      </div>

      {/* Distribution (donut) + Reliability — two column */}
      <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
        <DistributionPanel range={range} />
        <ReliabilityPanel range={range} />
      </div>

      {/* Error heatmap — full width */}
      <ErrorHeatmapPanel range={range} />
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
