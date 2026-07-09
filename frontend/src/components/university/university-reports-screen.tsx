"use client";

import * as React from "react";
import { useLocale, useTranslations } from "next-intl";
import { useQuery } from "@tanstack/react-query";
import {
  Activity,
  Award,
  BarChart3,
  Briefcase,
  Building2,
  CalendarDays,
  ClipboardList,
  Download,
  GraduationCap,
  Layers,
  Minus,
  Sparkles,
  TrendingDown,
  TrendingUp,
  Users,
} from "lucide-react";
import { Button } from "@/components/ui";
import {
  AreaChart,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  CardToolbar,
  DataTable,
  type ColumnDef,
  DonutChart,
  EmptyState,
  HorizontalBars,
  type HorizontalBarDatum,
  KpiRow,
  KpiTile,
  PageHeader,
  RadialChart,
  StatusChip,
} from "@/components/kit";
import {
  ApiError,
  careerOutcomesApi,
  dashboardsApi,
  type CareerOutcomeKpi,
  type CareerOutcomeRecord,
  type UniversityMarketIntelligence,
  type UniversityPlatformStats,
} from "@/lib/api";
import { formatRelativeTime } from "@/lib/format";

const nf = new Intl.NumberFormat();

function fmtDate(iso: string | null | undefined, locale: string): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  try {
    return new Intl.DateTimeFormat(locale === "vi" ? "vi-VN" : "en-US", { dateStyle: "medium" }).format(d);
  } catch {
    return iso;
  }
}

/* -------------------------------------------------------------------------- */
/* Screen                                                                      */
/* -------------------------------------------------------------------------- */

/**
 * University platform reports (v10). Governance + hiring-market intelligence +
 * career-outcomes reporting on the locked kit: platform KPI row → applications
 * trend + hiring-market snapshot (with an optional masked AI briefing) → skill
 * demand + employment-type mix → career-outcomes distribution, top employers,
 * and a privacy-safe outcomes table with a verification filter + CSV export.
 * The market read is a fixed aggregate snapshot and the career-outcomes reads
 * are a separate permission gate; every widget degrades honestly and no number
 * is ever fabricated.
 */
export function UniversityReportsScreen() {
  const t = useTranslations("universityReports");
  const tStates = useTranslations("states");
  const tc = useTranslations("common");
  const locale = useLocale();

  const [trustLevel, setTrustLevel] = React.useState<number | null>(null);

  const reportsQ = useQuery({
    queryKey: ["dashboard", "university", "reports"],
    queryFn: () => dashboardsApi.universityReports(),
    staleTime: 60_000,
    retry: false,
  });
  const marketQ = useQuery({
    queryKey: ["dashboard", "university", "market-intelligence"],
    queryFn: () => dashboardsApi.marketIntelligence(),
    staleTime: 60_000,
    retry: false,
  });
  const outcomesQ = useQuery({
    queryKey: ["dashboard", "university", "career-outcomes-kpi", locale],
    queryFn: () => careerOutcomesApi.getKpi(locale),
    staleTime: 60_000,
    retry: false,
  });
  const recordsQ = useQuery({
    queryKey: ["dashboard", "university", "career-outcomes-records", locale, trustLevel],
    queryFn: () => careerOutcomesApi.listRecords(locale, trustLevel ?? undefined),
    staleTime: 60_000,
    retry: false,
    enabled: !outcomesQ.isError,
  });

  const header = (
    <PageHeader
      title={t("title")}
      subtitle={t("subtitle")}
      meta={
        marketQ.data ? (
          <>
            <span className="inline-flex items-center gap-1.5">
              <Activity className="size-3.5" strokeWidth={1.8} />
              {t("metaUpdated", { time: formatRelativeTime(marketQ.data.computed_at, locale) })}
            </span>
            {marketQ.data.stale && <StatusChip tone="warning" size="sm">{t("metaStale")}</StatusChip>}
          </>
        ) : undefined
      }
      actions={
        <Button
          variant="secondary"
          size="sm"
          onClick={() => exportCsv({ reports: reportsQ.data, market: marketQ.data, outcomes: outcomesQ.data }, t("exportFilename"))}
          disabled={!reportsQ.data}
        >
          <Download className="size-4" strokeWidth={1.8} />
          {t("export")}
        </Button>
      }
    />
  );

  /* Permission / auth on the base reports read */
  if (reportsQ.isError && reportsQ.error instanceof ApiError) {
    const err = reportsQ.error;
    if (err.isPermissionError || err.isAuthError) {
      return (
        <>
          {header}
          <EmptyState
            kind={err.isPermissionError ? "permission" : "auth"}
            title={err.isPermissionError ? tStates("permissionTitle") : tStates("authTitle")}
            description={err.isPermissionError ? tStates("permissionBody") : tStates("authBody")}
          />
        </>
      );
    }
  }

  if (reportsQ.isPending) {
    return (
      <>
        {header}
        <ReportsSkeleton />
      </>
    );
  }

  if (reportsQ.isError || !reportsQ.data) {
    return (
      <>
        {header}
        <EmptyState
          kind="error"
          title={tStates("errorTitle")}
          description={tStates("errorBody")}
          action={
            <Button variant="secondary" onClick={() => void reportsQ.refetch()}>
              {tc("retry")}
            </Button>
          }
        />
      </>
    );
  }

  const reports = reportsQ.data;

  return (
    <>
      {header}
      <div className="space-y-4">
        {/* KPI row */}
        <KpiRow cols={5}>
          <KpiTile label={t("kpiStudents")} value={nf.format(reports.kpis.students)} icon={Users} />
          <KpiTile label={t("kpiPartners")} value={nf.format(reports.kpis.partner_members)} icon={Building2} />
          <KpiTile label={t("kpiJobs")} value={nf.format(reports.kpis.jobs)} icon={Briefcase} />
          <KpiTile label={t("kpiApplications")} value={nf.format(reports.kpis.applications)} icon={ClipboardList} />
          <KpiTile label={t("kpiEvents")} value={nf.format(reports.kpis.events)} icon={CalendarDays} />
        </KpiRow>

        {/* Trend + market */}
        <div className="grid gap-4 lg:grid-cols-3">
          <TrendCard reports={reports} className="lg:col-span-2" />
          <MarketCard market={marketQ.data} loading={marketQ.isPending} />
        </div>

        {/* AI market briefing (masked, advisory) */}
        {marketQ.data?.ai_narrative_available && marketQ.data.ai_narrative && (
          <MarketBriefingCard text={marketQ.data.ai_narrative} />
        )}

        {/* Skill demand + employment mix */}
        <div className="grid gap-4 lg:grid-cols-2">
          <SkillsCard market={marketQ.data} loading={marketQ.isPending} />
          <EmploymentTypesCard market={marketQ.data} loading={marketQ.isPending} />
        </div>

        {/* Career outcomes */}
        <OutcomesSection
          outcomes={outcomesQ.data}
          outcomesLoading={outcomesQ.isPending}
          outcomesError={outcomesQ.error}
          records={recordsQ.data?.items ?? []}
          recordsLoading={recordsQ.isPending && !outcomesQ.isError}
          trustLevel={trustLevel}
          onTrustLevel={setTrustLevel}
          locale={locale}
        />
      </div>
    </>
  );
}

/* -------------------------------------------------------------------------- */
/* Applications trend                                                          */
/* -------------------------------------------------------------------------- */

function TrendCard({ reports, className }: { reports: UniversityPlatformStats; className?: string }) {
  const t = useTranslations("universityReports");
  const monthly = reports.monthly_applications;
  return (
    <Card className={className}>
      <CardHeader>
        <div>
          <CardTitle>{t("trend.title")}</CardTitle>
          <CardDescription>{t("trend.subtitle")}</CardDescription>
        </div>
        <CardToolbar>
          <Activity className="size-4 text-muted-foreground" strokeWidth={1.8} />
        </CardToolbar>
      </CardHeader>
      <CardContent>
        {monthly.length === 0 ? (
          <p className="type-small text-muted-foreground">{t("trend.empty")}</p>
        ) : (
          <>
            <AreaChart
              data={monthly.map((p) => ({ month: p.label, count: p.count }))}
              xKey="month"
              series={[{ key: "count", label: t("trend.series"), color: "var(--viz-indigo)" }]}
              height={240}
              formatValue={(v) => nf.format(v)}
              ariaLabel={t("trend.title")}
            />
            <table className="sr-only">
              <caption>{t("trend.srCaption")}</caption>
              <thead>
                <tr>
                  <th>{t("trend.colMonth")}</th>
                  <th>{t("trend.colApplications")}</th>
                </tr>
              </thead>
              <tbody>
                {monthly.map((p) => (
                  <tr key={p.month}>
                    <td>{p.label}</td>
                    <td>{p.count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        )}
      </CardContent>
    </Card>
  );
}

/* -------------------------------------------------------------------------- */
/* Hiring market snapshot                                                       */
/* -------------------------------------------------------------------------- */

function MarketCard({ market, loading }: { market: UniversityMarketIntelligence | undefined; loading: boolean }) {
  const t = useTranslations("universityReports");
  const TrendIcon = market?.trend === "up" ? TrendingUp : market?.trend === "down" ? TrendingDown : Minus;
  const trendLabel =
    market?.trend === "up" ? t("market.trendUp") : market?.trend === "down" ? t("market.trendDown") : t("market.trendFlat");
  const trendColor =
    market?.trend === "up"
      ? "var(--content-success)"
      : market?.trend === "down"
        ? "var(--content-danger)"
        : "var(--text-muted)";

  return (
    <Card>
      <CardHeader>
        <div>
          <CardTitle>{t("market.title")}</CardTitle>
          <CardDescription>{t("market.subtitle")}</CardDescription>
        </div>
        <CardToolbar>
          <BarChart3 className="size-4 text-muted-foreground" strokeWidth={1.8} />
        </CardToolbar>
      </CardHeader>
      <CardContent>
        {loading ? (
          <div className="h-[220px] animate-skeleton rounded-lg bg-[var(--bg-muted)]" />
        ) : !market || market.active_jobs === 0 ? (
          <EmptyState kind="empty" title={t("market.empty")} description={t("market.subtitle")} />
        ) : (
          <div className="space-y-4">
            <div className="grid grid-cols-2 items-center gap-3">
              <div>
                <p className="type-caption text-muted-foreground">{t("market.activeJobs")}</p>
                <p className="type-metric text-foreground">{nf.format(market.active_jobs)}</p>
                <div className="mt-1 flex items-center gap-1.5">
                  <span
                    className="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[0.6875rem] font-semibold"
                    style={{ background: "var(--bg-muted)", color: trendColor }}
                  >
                    <TrendIcon aria-hidden className="size-3" strokeWidth={2.2} />
                    {trendLabel}
                  </span>
                </div>
                <p className="type-caption mt-1.5 text-muted-foreground">
                  {t("market.posted30d")}: <span className="font-semibold tabular-nums text-foreground">{nf.format(market.jobs_last_30d)}</span>
                  {" · "}
                  {t("market.posted30dHint", { count: market.jobs_prev_30d })}
                </p>
              </div>
              <div>
                <RadialChart
                  value={market.salary_disclosure_rate}
                  height={130}
                  color="var(--viz-teal)"
                  centerLabel={t("market.salaryDisclosure")}
                  ariaLabel={t("market.salaryDisclosure")}
                />
              </div>
            </div>
            {market.low_signal && (
              <p className="rounded-lg bg-[var(--bg-subtle)] px-3 py-2 type-small text-muted-foreground">
                {t("market.lowSignal")}
              </p>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function MarketBriefingCard({ text }: { text: string }) {
  const t = useTranslations("universityReports");
  return (
    <Card className="border-l-[3px]" style={{ borderLeftColor: "var(--content-ai)" }}>
      <CardHeader>
        <div className="flex items-center gap-2">
          <span className="flex size-7 items-center justify-center rounded-lg" style={{ background: "var(--content-ai-soft)" }}>
            <Sparkles className="size-4" strokeWidth={1.9} style={{ color: "var(--content-ai)" }} />
          </span>
          <CardTitle>{t("market.aiSummaryTitle")}</CardTitle>
        </div>
      </CardHeader>
      <CardContent>
        <p className="type-caption mb-2 text-muted-foreground">{t("market.aiSummaryDisclaimer")}</p>
        <p className="whitespace-pre-line text-[0.8125rem] leading-relaxed text-foreground">{text}</p>
      </CardContent>
    </Card>
  );
}

/* -------------------------------------------------------------------------- */
/* Skill demand                                                                */
/* -------------------------------------------------------------------------- */

function SkillsCard({ market, loading }: { market: UniversityMarketIntelligence | undefined; loading: boolean }) {
  const t = useTranslations("universityReports");
  const skills = React.useMemo<HorizontalBarDatum[]>(
    () => (market?.top_skills ?? []).slice(0, 8).map((s) => ({ label: s.skill, value: s.count })),
    [market],
  );
  return (
    <Card>
      <CardHeader>
        <div>
          <CardTitle>{t("skills.title")}</CardTitle>
          <CardDescription>{t("skills.subtitle")}</CardDescription>
        </div>
        <CardToolbar>
          <BarChart3 className="size-4 text-muted-foreground" strokeWidth={1.8} />
        </CardToolbar>
      </CardHeader>
      <CardContent>
        {loading ? (
          <div className="h-40 animate-skeleton rounded-lg bg-[var(--bg-muted)]" />
        ) : skills.length === 0 ? (
          <EmptyState kind="empty" title={t("skills.empty")} description={t("skills.subtitle")} />
        ) : (
          <HorizontalBars data={skills} formatValue={(v) => nf.format(v)} ariaLabel={t("skills.title")} />
        )}
      </CardContent>
    </Card>
  );
}

/* -------------------------------------------------------------------------- */
/* Employment-type mix                                                          */
/* -------------------------------------------------------------------------- */

function EmploymentTypesCard({ market, loading }: { market: UniversityMarketIntelligence | undefined; loading: boolean }) {
  const t = useTranslations("universityReports");
  const humanize = (code: string) => code.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
  const label = (code: string) => (t.has(`empType.${code}`) ? t(`empType.${code}`) : humanize(code));

  const slices = React.useMemo(
    () => (market?.employment_types ?? []).map((e) => ({ label: label(e.type), value: e.count })),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [market],
  );
  const total = slices.reduce((s, d) => s + d.value, 0);

  return (
    <Card>
      <CardHeader>
        <div>
          <CardTitle>{t("employmentTypes.title")}</CardTitle>
          <CardDescription>{t("employmentTypes.subtitle")}</CardDescription>
        </div>
        <CardToolbar>
          <Layers className="size-4 text-muted-foreground" strokeWidth={1.8} />
        </CardToolbar>
      </CardHeader>
      <CardContent>
        {loading ? (
          <div className="h-[200px] animate-skeleton rounded-lg bg-[var(--bg-muted)]" />
        ) : slices.length === 0 || total === 0 ? (
          <EmptyState kind="empty" title={t("employmentTypes.empty")} description={t("employmentTypes.subtitle")} />
        ) : (
          <DonutChart
            data={slices}
            centerValue={nf.format(total)}
            centerLabel={t("employmentTypes.center")}
            formatValue={(v) => nf.format(v)}
          />
        )}
      </CardContent>
    </Card>
  );
}

/* -------------------------------------------------------------------------- */
/* Career outcomes                                                              */
/* -------------------------------------------------------------------------- */

function OutcomesSection({
  outcomes,
  outcomesLoading,
  outcomesError,
  records,
  recordsLoading,
  trustLevel,
  onTrustLevel,
  locale,
}: {
  outcomes: CareerOutcomeKpi | undefined;
  outcomesLoading: boolean;
  outcomesError: unknown;
  records: CareerOutcomeRecord[];
  recordsLoading: boolean;
  trustLevel: number | null;
  onTrustLevel: (v: number | null) => void;
  locale: string;
}) {
  const t = useTranslations("universityReports");

  const locked = outcomesError instanceof ApiError && (outcomesError.isPermissionError || outcomesError.isAuthError);
  if (locked) {
    return (
      <Card>
        <CardHeader>
          <div className="flex items-center gap-2">
            <GraduationCap className="size-4 text-muted-foreground" strokeWidth={1.8} />
            <CardTitle>{t("outcomes.sectionTitle")}</CardTitle>
          </div>
        </CardHeader>
        <CardContent>
          <EmptyState kind="permission" title={t("outcomes.lockedTitle")} description={t("outcomes.lockedBody")} />
        </CardContent>
      </Card>
    );
  }

  const trustSlices = (outcomes?.by_trust_level ?? [])
    .filter((b) => b.count > 0)
    .map((b) => ({ label: b.label, value: b.count }));
  const employers: HorizontalBarDatum[] = (outcomes?.top_employers ?? [])
    .slice(0, 8)
    .map((e) => ({ label: e.employer_name, value: e.count }));

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <GraduationCap className="size-4 text-muted-foreground" strokeWidth={1.8} />
        <h2 className="type-h3 text-foreground">{t("outcomes.sectionTitle")}</h2>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        {/* By trust level */}
        <Card>
          <CardHeader>
            <div>
              <CardTitle>{t("outcomes.byTrustTitle")}</CardTitle>
              <CardDescription>{t("outcomes.byTrustSubtitle")}</CardDescription>
            </div>
            <CardToolbar>
              <Layers className="size-4 text-muted-foreground" strokeWidth={1.8} />
            </CardToolbar>
          </CardHeader>
          <CardContent>
            {outcomesLoading ? (
              <div className="h-[200px] animate-skeleton rounded-lg bg-[var(--bg-muted)]" />
            ) : trustSlices.length === 0 ? (
              <EmptyState kind="empty" title={t("outcomes.byTrustEmpty")} description={t("outcomes.byTrustSubtitle")} />
            ) : (
              <DonutChart
                data={trustSlices}
                centerValue={nf.format(outcomes?.total_outcomes ?? 0)}
                centerLabel={t("outcomes.byTrustCenter")}
                formatValue={(v) => nf.format(v)}
              />
            )}
          </CardContent>
        </Card>

        {/* Top employers */}
        <Card>
          <CardHeader>
            <div>
              <CardTitle>{t("outcomes.employersTitle")}</CardTitle>
              <CardDescription>{t("outcomes.employersSubtitle")}</CardDescription>
            </div>
            <CardToolbar>
              <Award className="size-4 text-muted-foreground" strokeWidth={1.8} />
            </CardToolbar>
          </CardHeader>
          <CardContent>
            {outcomesLoading ? (
              <div className="h-40 animate-skeleton rounded-lg bg-[var(--bg-muted)]" />
            ) : employers.length === 0 ? (
              <EmptyState kind="empty" title={t("outcomes.employersEmpty")} description={t("outcomes.employersSubtitle")} />
            ) : (
              <HorizontalBars data={employers} formatValue={(v) => nf.format(v)} ariaLabel={t("outcomes.employersTitle")} />
            )}
          </CardContent>
        </Card>
      </div>

      {/* Records table */}
      <OutcomesRecordsCard
        outcomes={outcomes}
        records={records}
        recordsLoading={recordsLoading}
        trustLevel={trustLevel}
        onTrustLevel={onTrustLevel}
        locale={locale}
      />
    </div>
  );
}

function OutcomesRecordsCard({
  outcomes,
  records,
  recordsLoading,
  trustLevel,
  onTrustLevel,
  locale,
}: {
  outcomes: CareerOutcomeKpi | undefined;
  records: CareerOutcomeRecord[];
  recordsLoading: boolean;
  trustLevel: number | null;
  onTrustLevel: (v: number | null) => void;
  locale: string;
}) {
  const t = useTranslations("universityReports");
  const trustOptions = outcomes?.by_trust_level ?? [];

  const cols: ColumnDef<CareerOutcomeRecord, unknown>[] = [
    {
      accessorKey: "position_title",
      header: t("outcomes.colPosition"),
      cell: ({ row }) => (
        <span className="font-medium text-foreground">
          {row.original.position_title ?? t("outcomes.unknownPosition")}
        </span>
      ),
    },
    {
      accessorKey: "employer_name",
      header: t("outcomes.colEmployer"),
      cell: ({ row }) => <span className="text-muted-foreground">{row.original.employer_name}</span>,
    },
    {
      accessorKey: "start_date",
      header: t("outcomes.colStart"),
      meta: { align: "right" },
      cell: ({ row }) => <span className="tabular-nums text-muted-foreground">{fmtDate(row.original.start_date, locale)}</span>,
    },
    {
      accessorKey: "outcome",
      header: t("outcomes.colOutcome"),
      cell: ({ row }) => <span className="text-foreground">{row.original.outcome}</span>,
    },
    {
      accessorKey: "trust_label",
      header: t("outcomes.colTrust"),
      cell: ({ row }) => (
        <StatusChip tone="neutral" size="sm">
          {row.original.trust_label}
        </StatusChip>
      ),
    },
    {
      accessorKey: "recorded_at",
      header: t("outcomes.colRecorded"),
      meta: { align: "right" },
      cell: ({ row }) => <span className="tabular-nums text-muted-foreground">{fmtDate(row.original.recorded_at, locale)}</span>,
    },
  ];

  return (
    <Card>
      <CardHeader className="flex-col items-stretch gap-3 sm:flex-row sm:items-center">
        <div>
          <CardTitle>{t("outcomes.recordsTitle")}</CardTitle>
          <CardDescription>{t("outcomes.recordsSubtitle")}</CardDescription>
        </div>
        <CardToolbar className="flex-wrap">
          <div
            className="inline-flex flex-wrap items-center rounded-lg border border-border bg-card p-0.5"
            role="group"
            aria-label={t("outcomes.filterLabel")}
          >
            <button
              type="button"
              onClick={() => onTrustLevel(null)}
              aria-pressed={trustLevel === null}
              className={
                "rounded-md px-2.5 py-1 text-[0.8125rem] font-medium transition-colors " +
                (trustLevel === null ? "bg-[var(--bg-subtle)] text-foreground" : "text-muted-foreground hover:text-foreground")
              }
            >
              {t("outcomes.filterAll")}
            </button>
            {trustOptions.map((b) => (
              <button
                key={b.trust_level}
                type="button"
                onClick={() => onTrustLevel(b.trust_level)}
                aria-pressed={trustLevel === b.trust_level}
                className={
                  "rounded-md px-2.5 py-1 text-[0.8125rem] font-medium transition-colors " +
                  (trustLevel === b.trust_level ? "bg-[var(--bg-subtle)] text-foreground" : "text-muted-foreground hover:text-foreground")
                }
              >
                {b.label}
              </button>
            ))}
          </div>
        </CardToolbar>
      </CardHeader>
      <CardContent>
        <DataTable
          columns={cols}
          data={records}
          getRowId={(r) => r.id}
          loading={recordsLoading}
          pageSize={10}
          empty={<EmptyState kind="empty" title={t("outcomes.recordsEmpty")} description={t("outcomes.recordsEmptyBody")} />}
        />
      </CardContent>
    </Card>
  );
}

/* -------------------------------------------------------------------------- */
/* CSV export                                                                   */
/* -------------------------------------------------------------------------- */

function exportCsv(
  data: {
    reports: UniversityPlatformStats | undefined;
    market: UniversityMarketIntelligence | undefined;
    outcomes: CareerOutcomeKpi | undefined;
  },
  filename: string,
) {
  const { reports, market, outcomes } = data;
  if (!reports) return;
  const lines: string[] = [];
  const esc = (v: string | number) => `"${String(v).replace(/"/g, '""')}"`;
  lines.push("section,label,value");
  for (const [k, v] of Object.entries(reports.kpis)) lines.push(["kpi", k, v].map(esc).join(","));
  for (const m of reports.monthly_applications) lines.push(["monthly", m.label, m.count].map(esc).join(","));
  if (market) {
    lines.push(["market", "active_jobs", market.active_jobs].map(esc).join(","));
    lines.push(["market", "jobs_last_30d", market.jobs_last_30d].map(esc).join(","));
    lines.push(["market", "jobs_prev_30d", market.jobs_prev_30d].map(esc).join(","));
    lines.push(["market", "salary_disclosure_rate", market.salary_disclosure_rate].map(esc).join(","));
    for (const s of market.top_skills) lines.push(["skill", s.skill, s.count].map(esc).join(","));
    for (const e of market.employment_types) lines.push(["employment_type", e.type, e.count].map(esc).join(","));
  }
  if (outcomes) {
    lines.push(["outcome", "total", outcomes.total_outcomes].map(esc).join(","));
    for (const b of outcomes.by_trust_level) lines.push(["outcome_trust", b.label, b.count].map(esc).join(","));
    for (const e of outcomes.top_employers) lines.push(["outcome_employer", e.employer_name, e.count].map(esc).join(","));
  }
  const blob = new Blob([lines.join("\n")], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `${filename}.csv`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

/* -------------------------------------------------------------------------- */
/* Skeleton                                                                     */
/* -------------------------------------------------------------------------- */

function ReportsSkeleton() {
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 sm:gap-4 lg:grid-cols-5">
        {Array.from({ length: 5 }).map((_, i) => (
          <div key={i} className="h-[86px] animate-skeleton rounded-xl bg-[var(--bg-muted)]" />
        ))}
      </div>
      <div className="grid gap-4 lg:grid-cols-3">
        <div className="h-72 animate-skeleton rounded-xl bg-[var(--bg-muted)] lg:col-span-2" />
        <div className="h-72 animate-skeleton rounded-xl bg-[var(--bg-muted)]" />
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        <div className="h-64 animate-skeleton rounded-xl bg-[var(--bg-muted)]" />
        <div className="h-64 animate-skeleton rounded-xl bg-[var(--bg-muted)]" />
      </div>
    </div>
  );
}
