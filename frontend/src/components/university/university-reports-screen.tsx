"use client";

import { useTranslations } from "next-intl";
import { useQuery } from "@tanstack/react-query";
import {
  Briefcase,
  Buildings,
  Calendar,
  ChartBar,
  ClipboardText,
  LightbulbFilament,
  ShieldWarning,
  SignIn,
  Sparkle,
  TrendUp,
  Users,
  WarningCircle,
} from "@phosphor-icons/react";
import { Button, EmptyState, Skeleton } from "@/components/ui";
import { PageHeader } from "@/components/layout/page-header";
import { ApiError, dashboardsApi } from "@/lib/api";

export function UniversityReportsScreen() {
  const t = useTranslations("universityReports");
  const tc = useTranslations("common");
  const tStates = useTranslations("states");

  const query = useQuery({
    queryKey: ["dashboards", "university", "reports"],
    queryFn: () => dashboardsApi.universityReports(),
    staleTime: 60_000,
    retry: false,
  });

  if (query.isError && query.error instanceof ApiError) {
    const err = query.error;
    if (err.isPermissionError || err.isAuthError) {
      return (
        <>
          <PageHeader title={t("title")} description={t("subtitle")} />
          <EmptyState
            kind={err.isPermissionError ? "permission" : "auth"}
            icon={err.isPermissionError ? ShieldWarning : SignIn}
            title={
              err.isPermissionError
                ? tStates("permissionTitle")
                : tStates("authTitle")
            }
            description={
              err.isPermissionError
                ? tStates("permissionBody")
                : tStates("authBody")
            }
          />
        </>
      );
    }
    return (
      <>
        <PageHeader title={t("title")} description={t("subtitle")} />
        <EmptyState
          kind="error"
          icon={WarningCircle}
          title={tStates("errorTitle")}
          description={tStates("errorBody")}
          action={
            <Button variant="secondary" onClick={() => void query.refetch()}>
              {tc("retry")}
            </Button>
          }
        />
      </>
    );
  }

  const data = query.data;
  const kpis = data?.kpis;
  const monthly = data?.monthly_applications ?? [];
  const isPending = query.isPending;

  const maxCount = monthly.length > 0 ? Math.max(...monthly.map((m) => m.count), 1) : 1;

  function deriveInsights(): string[] {
    if (!kpis) return [];
    const insights: string[] = [];
    const appsPerJob = kpis.jobs > 0 ? Math.round(kpis.applications / kpis.jobs) : 0;
    if (appsPerJob >= 10) insights.push(t("aiInsightStrongDemand", { count: appsPerJob }));
    else if (kpis.jobs > 0 && appsPerJob < 5) insights.push(t("aiInsightLowVolume", { count: appsPerJob }));
    if (monthly.length >= 2) {
      const last = monthly[monthly.length - 1]?.count ?? 0;
      const prev = monthly[monthly.length - 2]?.count ?? 0;
      if (prev > 0 && last > prev * 1.2) insights.push(t("aiInsightTrendUp", { pct: Math.round(((last - prev) / prev) * 100) }));
      else if (prev > 0 && last < prev * 0.8) insights.push(t("aiInsightTrendDown", { pct: Math.round(((prev - last) / prev) * 100) }));
    }
    if (kpis.events >= 3) insights.push(t("aiInsightEvents", { count: kpis.events }));
    if (kpis.partner_members > 0 && kpis.jobs > 0) {
      const jobsPerPartner = Math.round(kpis.jobs / kpis.partner_members);
      if (jobsPerPartner >= 3) insights.push(t("aiInsightActivePartners", { count: jobsPerPartner }));
    }
    return insights.slice(0, 3);
  }
  const aiInsights = deriveInsights();

  return (
    <div className="flex flex-col gap-6">
      <PageHeader title={t("title")} description={t("subtitle")} />

      {/* ── KPI tiles ── */}
      <section aria-label={t("kpisLabel")}>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
          <KpiTile
            icon={Users}
            label={t("kpiStudents")}
            value={isPending ? null : (kpis?.students ?? 0)}
            iconBg="icon-chip-primary"
          />
          <KpiTile
            icon={Buildings}
            label={t("kpiPartners")}
            value={isPending ? null : (kpis?.partner_members ?? 0)}
            iconBg="icon-chip-info"
          />
          <KpiTile
            icon={Briefcase}
            label={t("kpiJobs")}
            value={isPending ? null : (kpis?.jobs ?? 0)}
            iconBg="icon-chip-success"
          />
          <KpiTile
            icon={ClipboardText}
            label={t("kpiApplications")}
            value={isPending ? null : (kpis?.applications ?? 0)}
            iconBg="icon-chip-warning"
          />
          <KpiTile
            icon={Calendar}
            label={t("kpiEvents")}
            value={isPending ? null : (kpis?.events ?? 0)}
            iconBg="icon-chip-success"
          />
        </div>
      </section>

      {/* ── Platform insights ── */}
      {!isPending && aiInsights.length > 0 && (
        <section
          aria-label={t("aiInsightsTitle")}
          className="rounded-2xl border border-[var(--ai-accent)]/25 bg-gradient-to-br from-[var(--ai-accent-soft)] to-white/60 p-5 "
        >
          <div className="mb-3 flex items-center gap-2">
            <div className="icon-chip-success flex size-8 items-center justify-center rounded-lg shadow-sm">
              <Sparkle aria-hidden weight="duotone" className="size-4 text-white" />
            </div>
            <h2 className="text-sm font-bold text-[var(--text-primary)]">{t("aiInsightsTitle")}</h2>
            <TrendUp aria-hidden weight="bold" className="ml-auto size-4 text-[var(--ai-accent)]" />
          </div>
          <ul className="space-y-2">
            {aiInsights.map((insight, i) => (
              <li key={i} className="flex items-start gap-2 text-sm text-[var(--text-secondary)]">
                <LightbulbFilament aria-hidden weight="duotone" className="mt-0.5 size-4 shrink-0 text-[var(--ai-accent)]" />
                {insight}
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* ── Monthly applications bar chart ── */}
      <section
        aria-label={t("monthlyLabel")}
        className="rounded-2xl border border-[var(--border-default)] bg-white p-5 "
      >
        <div className="mb-4 flex items-center gap-2.5">
          <span className="flex size-7 shrink-0 items-center justify-center rounded-lg icon-chip-primary shadow-sm">
            <ChartBar aria-hidden weight="duotone" className="size-4 text-white" />
          </span>
          <h2 className="text-sm font-bold text-[var(--text-primary)]">
            {t("monthlyLabel")}
          </h2>
        </div>

        {isPending ? (
          <div className="flex items-end gap-2 h-40" aria-hidden>
            {Array.from({ length: 6 }).map((_, i) => (
              <div key={i} className="flex-1 flex flex-col items-center gap-1">
                <Skeleton className="w-full" style={{ height: `${(i + 1) * 20}px` }} />
                <Skeleton className="h-3 w-10" />
              </div>
            ))}
          </div>
        ) : monthly.length === 0 ? (
          <p className="py-8 text-center text-sm text-[var(--text-muted)]">
            {t("monthlyEmpty")}
          </p>
        ) : (
          <div className="flex items-end gap-2" style={{ height: "160px" }}>
            {monthly.map((m) => {
              const pct = maxCount > 0 ? (m.count / maxCount) * 100 : 0;
              return (
                <div
                  key={m.month}
                  className="flex flex-1 flex-col items-center justify-end gap-1"
                  style={{ height: "100%" }}
                >
                  <span className="text-[10px] font-semibold tabular-nums text-[var(--text-secondary)]">
                    {m.count > 0 ? m.count : ""}
                  </span>
                  <div
                    className="w-full min-h-[4px] rounded-t-md bg-[var(--brand-primary)]/70 transition-all"
                    style={{ height: `${Math.max(pct, 2)}%` }}
                    title={`${m.label}: ${m.count}`}
                  />
                  <span className="text-[10px] text-[var(--text-muted)] text-center leading-tight">
                    {m.label.split(" ")[0]}
                  </span>
                </div>
              );
            })}
          </div>
        )}
      </section>
    </div>
  );
}

/* ─── KPI tile ──────────────────────────────────────────────────────────── */

function KpiTile({
  icon: Icon,
  label,
  value,
  iconBg,
}: {
  icon: React.ElementType;
  label: string;
  value: number | null;
  iconBg: string;
}) {
  return (
    <div className="rounded-2xl border border-[var(--border-default)] bg-white px-4 py-4 shadow-[0_2px_16px_rgba(11,34,57,0.06)] transition-all hover:-translate-y-0.5 hover:shadow-[0_6px_24px_rgba(11,34,57,0.10)]">
      <div className={`mb-3 flex size-10 items-center justify-center rounded-xl shadow-sm ${iconBg}`}>
        <Icon aria-hidden weight="duotone" className="size-5 text-white" />
      </div>
      {value === null ? (
        <Skeleton className="mb-1 h-8 w-16" />
      ) : (
        <p className="text-3xl font-black tracking-tight text-[var(--text-primary)]">
          {value.toLocaleString()}
        </p>
      )}
      <p className="mt-0.5 text-xs font-medium text-[var(--text-secondary)]">{label}</p>
    </div>
  );
}
