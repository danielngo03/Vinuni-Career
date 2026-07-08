"use client";

import { useState, useCallback } from "react";
import { useTranslations } from "next-intl";
import { useQuery } from "@tanstack/react-query";
import {
  UsersThree,
  Briefcase,
  ClipboardText,
  CalendarBlank,
  Buildings,
  GraduationCap,
  WarningCircle,
  TrendUp,
  FunnelSimple,
} from "@phosphor-icons/react";
import { PageHeader } from "@/components/layout/page-header";
import {
  SegmentedControl,
  Skeleton,
  SkeletonCard,
  EmptyState,
} from "@/components/ui";
import { TimeSeriesChart } from "@/components/ui/charts";
import type { TimeSeriesDataPoint } from "@/components/ui/charts";
import {
  adminAnalyticsApi,
  type AdminAnalyticsFunnelStage,
} from "@/lib/api/admin-analytics";
import { cn } from "@/lib/utils";

/* -------------------------------------------------------------------------- */
/* Range type and helper                                                       */
/* -------------------------------------------------------------------------- */

type AnalyticsRange = "7d" | "30d";

function rangeToDays(range: AnalyticsRange): number {
  return range === "7d" ? 7 : 30;
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
  const id = `analytics-panel-${title
    .toLowerCase()
    .replace(/\s+/g, "-")
    .replace(/[^a-z0-9-]/g, "")}`;
  return (
    <section
      aria-labelledby={id}
      className={cn("marketplace-card rounded-[12px] p-5", className)}
    >
      <h2
        id={id}
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
/* KPI Metric tile                                                            */
/* -------------------------------------------------------------------------- */

function KpiTile({
  label,
  value,
  icon: Icon,
}: {
  label: string;
  value: number;
  icon: React.ElementType;
}) {
  return (
    <div className="marketplace-card flex flex-col rounded-[12px] px-4 py-3.5">
      <div className="flex items-start justify-between gap-2">
        <span className="truncate text-[0.8125rem] font-medium text-[var(--text-secondary)]">
          {label}
        </span>
        <span className="icon-chip-primary flex size-7 shrink-0 items-center justify-center rounded-lg">
          <Icon aria-hidden weight="duotone" className="size-4" />
        </span>
      </div>
      <span
        className="mt-1.5 font-mono text-[1.75rem] font-bold leading-none tracking-tight tabular-nums text-[var(--text-primary)]"
        style={{ fontFamily: "'JetBrains Mono', ui-monospace, monospace" }}
      >
        {new Intl.NumberFormat().format(value)}
      </span>
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* KPI tiles panel                                                            */
/* -------------------------------------------------------------------------- */

function KpiPanel() {
  const t = useTranslations("adminConsole.analytics");

  const query = useQuery({
    queryKey: ["admin-analytics", "kpis"] as const,
    queryFn: () => adminAnalyticsApi.kpis(),
    staleTime: 60_000,
    retry: 1,
  });

  if (query.isPending) {
    return (
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6">
        {Array.from({ length: 6 }).map((_, i) => (
          <SkeletonCard key={i} />
        ))}
      </div>
    );
  }

  if (query.isError) {
    return (
      <div className="marketplace-card rounded-[12px] p-5">
        <EmptyState
          kind="error"
          icon={WarningCircle}
          title={t("kpi.errorTitle")}
          description={t("kpi.errorBody")}
          action={
            <button
              onClick={() => void query.refetch()}
              className="text-xs font-semibold text-[var(--brand-primary)] underline-offset-2 hover:underline"
            >
              {t("retry")}
            </button>
          }
        />
      </div>
    );
  }

  const data = query.data;

  return (
    <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6">
      <KpiTile label={t("kpi.students")} value={data.students} icon={GraduationCap} />
      <KpiTile label={t("kpi.partnerMembers")} value={data.partner_members} icon={Buildings} />
      <KpiTile label={t("kpi.universityStaff")} value={data.university_staff} icon={UsersThree} />
      <KpiTile label={t("kpi.jobs")} value={data.jobs} icon={Briefcase} />
      <KpiTile label={t("kpi.applications")} value={data.applications} icon={ClipboardText} />
      <KpiTile label={t("kpi.events")} value={data.events} icon={CalendarBlank} />
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* Funnel bar list                                                             */
/* -------------------------------------------------------------------------- */

/**
 * A horizontal labeled bar list for the recruitment funnel.
 * Width is proportional to count relative to the first stage (top-of-funnel).
 * Conversion rate is displayed between stages when non-null.
 * Color fades from ink at the top to lighter gray downward.
 */
function FunnelBarList({
  stages,
  stageLabel,
  conversionLabel,
}: {
  stages: AdminAnalyticsFunnelStage[];
  stageLabel: (stage: AdminAnalyticsFunnelStage["stage"]) => string;
  conversionLabel: (pct: string) => string;
}) {
  if (stages.length === 0) return null;

  const topCount = stages[0]?.count ?? 1;

  // Monochrome ramp: first stage = ink (#171717), fading to light gray at bottom
  const stageColors = [
    "#171717",
    "#262626",
    "#404040",
    "#525252",
    "#737373",
    "#a3a3a3",
    "#d4d4d4",
    "#e5e5e5",
  ];

  return (
    <ol className="space-y-1" role="list" aria-label="Recruitment funnel stages">
      {stages.map((stage, idx) => {
        const widthPct =
          topCount > 0 ? Math.max((stage.count / topCount) * 100, 2) : 2;
        const color = stageColors[Math.min(idx, stageColors.length - 1)] ?? "#e5e5e5";
        const prevConversion = stage.conversion_from_previous;

        return (
          <li key={stage.stage}>
            {/* Conversion rate between stages */}
            {prevConversion !== null && idx > 0 && (
              <div
                className="mb-1 ml-[3.5rem] flex items-center gap-1.5"
                aria-label={`Conversion from previous stage: ${conversionLabel(
                  (prevConversion * 100).toFixed(1),
                )}`}
              >
                <span className="text-[0.6875rem] font-semibold tabular-nums text-[var(--text-muted)]">
                  {conversionLabel((prevConversion * 100).toFixed(1))}
                </span>
                <span
                  aria-hidden
                  className="h-px flex-1 border-t border-dashed border-[var(--border-subtle)]"
                />
              </div>
            )}

            {/* Stage bar row */}
            <div className="flex items-center gap-3">
              {/* Stage label */}
              <span className="w-44 shrink-0 truncate text-right text-[0.8125rem] font-medium text-[var(--text-secondary)]">
                {stageLabel(stage.stage)}
              </span>

              {/* Bar */}
              <div
                className="flex h-7 min-w-0 flex-1 items-center overflow-hidden rounded-[6px] bg-[var(--bg-muted)]"
                role="meter"
                aria-valuenow={stage.count}
                aria-valuemin={0}
                aria-valuemax={topCount}
                aria-label={`${stageLabel(stage.stage)}: ${new Intl.NumberFormat().format(stage.count)}`}
              >
                <div
                  className="flex h-full items-center rounded-[6px] px-2.5 transition-all duration-300"
                  style={{ width: `${widthPct}%`, backgroundColor: color }}
                >
                  <span
                    className="font-mono text-[0.6875rem] font-bold tabular-nums text-white"
                    style={{
                      fontFamily: "'JetBrains Mono', ui-monospace, monospace",
                      // Hide text if bar is too narrow to fit it
                      visibility: widthPct > 12 ? "visible" : "hidden",
                    }}
                  >
                    {new Intl.NumberFormat().format(stage.count)}
                  </span>
                </div>
              </div>

              {/* Count label (always visible) */}
              <span
                className="w-16 shrink-0 text-right font-mono text-[0.8125rem] font-bold tabular-nums text-[var(--text-primary)]"
                style={{ fontFamily: "'JetBrains Mono', ui-monospace, monospace" }}
              >
                {new Intl.NumberFormat().format(stage.count)}
              </span>
            </div>
          </li>
        );
      })}
    </ol>
  );
}

/* -------------------------------------------------------------------------- */
/* Funnel panel                                                                */
/* -------------------------------------------------------------------------- */

function FunnelPanel({ range }: { range: AnalyticsRange }) {
  const t = useTranslations("adminConsole.analytics");

  const rangeDays = rangeToDays(range);

  const query = useQuery({
    queryKey: ["admin-analytics", "funnel", rangeDays] as const,
    queryFn: () => adminAnalyticsApi.funnel(rangeDays),
    staleTime: 60_000,
    retry: 1,
  });

  if (query.isPending) {
    return (
      <PanelCard title={t("funnel.panelTitle")} icon={FunnelSimple}>
        <Skeleton className="h-64 w-full" />
      </PanelCard>
    );
  }

  if (query.isError) {
    return (
      <PanelCard title={t("funnel.panelTitle")} icon={FunnelSimple}>
        <EmptyState
          kind="error"
          icon={WarningCircle}
          title={t("funnel.errorTitle")}
          description={t("funnel.errorBody")}
          action={
            <button
              onClick={() => void query.refetch()}
              className="text-xs font-semibold text-[var(--brand-primary)] underline-offset-2 hover:underline"
            >
              {t("retry")}
            </button>
          }
        />
      </PanelCard>
    );
  }

  const stages = query.data?.stages ?? [];

  if (stages.length === 0) {
    return (
      <PanelCard title={t("funnel.panelTitle")} icon={FunnelSimple}>
        <div
          className="flex h-48 items-center justify-center rounded-lg border border-dashed border-[var(--border-default)] text-xs text-[var(--text-muted)]"
          role="img"
          aria-label={t("funnel.ariaLabel")}
        >
          {t("funnel.emptyLabel")}
        </div>
      </PanelCard>
    );
  }

  return (
    <PanelCard title={t("funnel.panelTitle")} icon={FunnelSimple}>
      <div role="img" aria-label={t("funnel.ariaLabel")}>
        <FunnelBarList
          stages={stages}
          stageLabel={(stage) => t(`funnel.stage.${stage}`)}
          conversionLabel={(pct) => t("funnel.conversionLabel", { pct })}
        />
      </div>
    </PanelCard>
  );
}

/* -------------------------------------------------------------------------- */
/* Growth panel                                                               */
/* -------------------------------------------------------------------------- */

function GrowthPanel({ range }: { range: AnalyticsRange }) {
  const t = useTranslations("adminConsole.analytics");

  const rangeDays = rangeToDays(range);

  const query = useQuery({
    queryKey: ["admin-analytics", "growth", rangeDays] as const,
    queryFn: () => adminAnalyticsApi.growth(rangeDays),
    staleTime: 60_000,
    retry: 1,
  });

  if (query.isPending) {
    return (
      <PanelCard title={t("growth.panelTitle")} icon={TrendUp}>
        <Skeleton className="h-56 w-full" />
      </PanelCard>
    );
  }

  if (query.isError) {
    return (
      <PanelCard title={t("growth.panelTitle")} icon={TrendUp}>
        <EmptyState
          kind="error"
          icon={WarningCircle}
          title={t("growth.errorTitle")}
          description={t("growth.errorBody")}
          action={
            <button
              onClick={() => void query.refetch()}
              className="text-xs font-semibold text-[var(--brand-primary)] underline-offset-2 hover:underline"
            >
              {t("retry")}
            </button>
          }
        />
      </PanelCard>
    );
  }

  const rows = query.data?.series ?? [];

  const tsData: TimeSeriesDataPoint[] = rows.map((r) => ({
    // Use MM-DD for axis brevity
    day: r.day.length >= 10 ? r.day.slice(5) : r.day,
    signups: r.signups,
    applications: r.applications,
    active_users: r.active_users,
  }));

  return (
    <PanelCard title={t("growth.panelTitle")} icon={TrendUp}>
      <TimeSeriesChart
        data={tsData}
        xKey="day"
        series={[
          {
            key: "active_users",
            label: t("growth.seriesActiveUsers"),
            type: "area",
            // ink — primary signal
          },
          {
            key: "signups",
            label: t("growth.seriesSignups"),
            type: "line",
            // theme-aware secondary series (see globals.css --chart-series-*)
            color: "var(--chart-series-2)",
          },
          {
            key: "applications",
            label: t("growth.seriesApplications"),
            type: "line",
            color: "var(--chart-series-3)",
          },
        ]}
        format="number"
        height={240}
        ariaLabel={t("growth.ariaLabel")}
        emptyLabel={t("growth.emptyLabel")}
      />
    </PanelCard>
  );
}

/* -------------------------------------------------------------------------- */
/* Main screen                                                                */
/* -------------------------------------------------------------------------- */

export function AnalyticsScreen() {
  const t = useTranslations("adminConsole.analytics");

  const [range, setRange] = useState<AnalyticsRange>("30d");

  const handleRangeChange = useCallback((v: string) => setRange(v as AnalyticsRange), []);

  const rangeOptions = [
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

      <div className="space-y-6">
        {/* KPI tiles — 6-up grid */}
        <KpiPanel />

        {/* Funnel + Growth — two columns on wide screens */}
        <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
          <FunnelPanel range={range} />
          <GrowthPanel range={range} />
        </div>
      </div>
    </>
  );
}
