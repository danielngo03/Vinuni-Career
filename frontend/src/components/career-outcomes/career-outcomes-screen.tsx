"use client";

import * as React from "react";
import { useLocale, useTranslations } from "next-intl";
import { useQuery } from "@tanstack/react-query";
import {
  Building2,
  GraduationCap,
  Info,
  Lightbulb,
  ShieldCheck,
  Sparkles,
  TrendingUp,
} from "lucide-react";
import { Button } from "@/components/ui";
import { PageHeader } from "@/components/layout/page-header";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardToolbar,
  DataTable,
  DonutChart,
  EmptyState,
  HorizontalBars,
  KpiRow,
  KpiTile,
  StatusChip,
  type ColumnDef,
  type DonutSlice,
  type HorizontalBarDatum,
} from "@/components/kit";
import { formatMonthYear } from "@/lib/format";
import {
  ApiError,
  careerOutcomesApi,
  type CareerOutcomeKpi,
  type CareerOutcomeRecord,
} from "@/lib/api";

const nf = new Intl.NumberFormat();

/** Below this many recorded outcomes the aggregates are too thin to read into. */
const LOW_SIGNAL_THRESHOLD = 10;

type CareerInsightKey =
  | "insightManyOutcomes"
  | "insightDiverseEmployers"
  | "insightHighTrust"
  | "insightNoOutcomes";

function deriveCareerInsights(
  totalOutcomes: number,
  topEmployers: number,
  highTrustCount: number,
): CareerInsightKey[] {
  const out: CareerInsightKey[] = [];
  if (totalOutcomes === 0) {
    out.push("insightNoOutcomes");
    return out;
  }
  if (totalOutcomes >= LOW_SIGNAL_THRESHOLD) out.push("insightManyOutcomes");
  if (topEmployers >= 5) out.push("insightDiverseEmployers");
  if (highTrustCount > 0) out.push("insightHighTrust");
  return out.slice(0, 3);
}

/* -------------------------------------------------------------------------- */
/* Screen                                                                      */
/* -------------------------------------------------------------------------- */

export function CareerOutcomesScreen() {
  const t = useTranslations("careerOutcomes");
  const tStates = useTranslations("states");
  const tc = useTranslations("common");
  const locale = useLocale();

  const query = useQuery({
    queryKey: ["university", "career-outcomes", "kpi", locale],
    queryFn: () => careerOutcomesApi.getKpi(locale),
    retry: false,
  });

  const header = <PageHeader title={t("title")} subtitle={t("subtitle")} />;

  /* ---- Permission / auth states ---- */
  if (query.isError && query.error instanceof ApiError) {
    const err = query.error;
    if (err.isPermissionError || err.isAuthError) {
      return (
        <>
          {header}
          <EmptyState
            kind={err.isPermissionError ? "permission" : "auth"}
            title={err.isPermissionError ? tStates("permissionTitle") : tStates("authTitle")}
            description={err.isPermissionError ? t("permissionBody") : tStates("authBody")}
          />
        </>
      );
    }
  }

  if (query.isPending) {
    return (
      <>
        {header}
        <OutcomesSkeleton />
      </>
    );
  }

  if (query.isError || !query.data) {
    return (
      <>
        {header}
        <EmptyState
          kind="error"
          title={tStates("errorTitle")}
          description={tStates("errorBody")}
          action={
            <Button variant="secondary" onClick={() => query.refetch()}>
              {tc("retry")}
            </Button>
          }
        />
      </>
    );
  }

  const data = query.data;
  const estimated = data.by_trust_level.find((b) => b.trust_level === 4)?.count ?? 0;
  const confirmed = Math.max(0, data.total_outcomes - estimated);
  const lowSignal = data.total_outcomes > 0 && data.total_outcomes < LOW_SIGNAL_THRESHOLD;

  return (
    <>
      {header}

      <div className="space-y-4">
        {/* Privacy provenance note — this surface holds no student PII / salary. */}
        <div className="flex items-start gap-2.5 rounded-xl border border-border bg-[var(--bg-subtle)] px-4 py-3">
          <ShieldCheck
            aria-hidden
            className="mt-0.5 size-4 shrink-0"
            strokeWidth={1.8}
            style={{ color: "var(--content-success)" }}
          />
          <p className="type-small text-muted-foreground">{t("privacyNote")}</p>
        </div>

        {/* KPI row — real aggregates only */}
        <KpiRow cols={4}>
          <KpiTile label={t("kpiTotal")} value={nf.format(data.total_outcomes)} icon={GraduationCap} />
          <KpiTile label={t("kpiEmployers")} value={nf.format(data.top_employers.length)} icon={Building2} />
          <KpiTile label={t("kpiConfirmed")} value={nf.format(confirmed)} icon={ShieldCheck} />
          <KpiTile label={t("kpiEstimated")} value={nf.format(estimated)} icon={TrendingUp} />
        </KpiRow>

        {lowSignal && (
          <div className="flex items-start gap-2.5 rounded-xl px-4 py-3" style={{ background: "var(--content-warning-soft)" }}>
            <Info aria-hidden className="mt-0.5 size-4 shrink-0" strokeWidth={1.9} style={{ color: "var(--content-warning)" }} />
            <div className="min-w-0">
              <p className="text-[0.8125rem] font-semibold text-foreground">{t("lowSignalTitle")}</p>
              <p className="type-caption mt-0.5 text-muted-foreground">{t("lowSignalBody", { count: data.total_outcomes })}</p>
            </div>
          </div>
        )}

        {/* Distribution charts */}
        <div className="grid gap-4 lg:grid-cols-2">
          <TrustMixCard data={data} />
          <TopEmployersCard data={data} />
        </div>

        {/* Recent outcomes table + AI insights rail */}
        <div className="grid gap-4 lg:grid-cols-3">
          <div className="lg:col-span-2">
            <RecentOutcomesCard rows={data.recent} locale={locale} />
          </div>
          <AiInsightsCard data={data} estimated={estimated} />
        </div>
      </div>
    </>
  );
}

/* -------------------------------------------------------------------------- */
/* Trust-level mix                                                             */
/* -------------------------------------------------------------------------- */

function TrustMixCard({ data }: { data: CareerOutcomeKpi }) {
  const t = useTranslations("careerOutcomes");
  const slices: DonutSlice[] = data.by_trust_level
    .filter((b) => b.count > 0)
    .map((b) => ({ label: b.label, value: b.count }));

  return (
    <Card>
      <CardHeader>
        <div>
          <CardTitle>{t("trustMixTitle")}</CardTitle>
        </div>
        <CardToolbar>
          <ShieldCheck className="size-4 text-muted-foreground" strokeWidth={1.8} />
        </CardToolbar>
      </CardHeader>
      <CardContent>
        {slices.length === 0 ? (
          <EmptyState kind="empty" title={t("empty")} description={t("emptyBody")} />
        ) : (
          <div className="flex flex-col items-center gap-4 sm:flex-row">
            <DonutChart
              className="w-full max-w-[220px]"
              data={slices}
              centerValue={nf.format(data.total_outcomes)}
              centerLabel={t("kpiTotal")}
              formatValue={(v) => nf.format(v)}
              ariaLabel={t("trustMixTitle")}
            />
            <ul className="w-full space-y-1.5">
              {data.by_trust_level.map((b, i) => (
                <li key={b.trust_level} className="flex items-center justify-between gap-3 text-[0.8125rem]">
                  <StatusChip tone={CHIP_ORDER[i % CHIP_ORDER.length]} dot size="sm">
                    {b.label}
                  </StatusChip>
                  <span className="font-semibold tabular-nums text-foreground">{nf.format(b.count)}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

const CHIP_ORDER = ["indigo", "teal", "amber", "rose", "sky", "emerald", "violet", "orange"] as const;

/* -------------------------------------------------------------------------- */
/* Top employers                                                               */
/* -------------------------------------------------------------------------- */

function TopEmployersCard({ data }: { data: CareerOutcomeKpi }) {
  const t = useTranslations("careerOutcomes");
  const bars: HorizontalBarDatum[] = data.top_employers
    .slice(0, 8)
    .map((e) => ({ label: e.employer_name, value: e.count }));

  return (
    <Card>
      <CardHeader>
        <div>
          <CardTitle>{t("topEmployersTitle")}</CardTitle>
        </div>
        <CardToolbar>
          <Building2 className="size-4 text-muted-foreground" strokeWidth={1.8} />
        </CardToolbar>
      </CardHeader>
      <CardContent>
        {bars.length === 0 ? (
          <EmptyState kind="empty" title={t("empty")} description={t("emptyBody")} />
        ) : (
          <HorizontalBars data={bars} formatValue={(v) => nf.format(v)} ariaLabel={t("topEmployersTitle")} />
        )}
      </CardContent>
    </Card>
  );
}

/* -------------------------------------------------------------------------- */
/* Recent outcomes table                                                       */
/* -------------------------------------------------------------------------- */

function RecentOutcomesCard({ rows, locale }: { rows: CareerOutcomeRecord[]; locale: string }) {
  const t = useTranslations("careerOutcomes");

  const columns: ColumnDef<CareerOutcomeRecord, unknown>[] = [
    {
      accessorKey: "position_title",
      header: t("colPosition"),
      cell: ({ row }) => (
        <span className="font-semibold text-foreground">
          {row.original.position_title ?? t("untitledPosition")}
        </span>
      ),
    },
    {
      accessorKey: "employer_name",
      header: t("colEmployer"),
      cell: ({ row }) => <span className="text-muted-foreground">{row.original.employer_name}</span>,
    },
    {
      accessorKey: "outcome",
      header: t("colOutcome"),
      cell: ({ row }) => (
        <StatusChip tone="success" size="sm">
          {row.original.outcome}
        </StatusChip>
      ),
    },
    {
      accessorKey: "trust_label",
      header: t("colTrust"),
      cell: ({ row }) => (
        <span className="inline-flex items-center gap-1.5 type-small text-muted-foreground">
          <ShieldCheck aria-hidden className="size-3.5" strokeWidth={1.8} />
          {row.original.trust_label}
        </span>
      ),
    },
    {
      accessorKey: "start_date",
      header: t("colStart"),
      meta: { align: "right" },
      cell: ({ row }) =>
        row.original.start_date ? (
          <span className="tabular-nums text-muted-foreground">
            {formatMonthYear(row.original.start_date, locale)}
          </span>
        ) : (
          <span className="text-muted-foreground">—</span>
        ),
    },
  ];

  return (
    <Card>
      <CardHeader>
        <div>
          <CardTitle>{t("recentTitle")}</CardTitle>
        </div>
      </CardHeader>
      <CardContent>
        <DataTable
          columns={columns}
          data={rows}
          getRowId={(r) => r.id}
          pageSize={8}
          empty={<EmptyState kind="empty" title={t("empty")} description={t("emptyBody")} />}
        />
      </CardContent>
    </Card>
  );
}

/* -------------------------------------------------------------------------- */
/* AI insights (advisory, derived from real aggregates)                        */
/* -------------------------------------------------------------------------- */

function AiInsightsCard({ data, estimated }: { data: CareerOutcomeKpi; estimated: number }) {
  const t = useTranslations("careerOutcomes");
  const insights = deriveCareerInsights(data.total_outcomes, data.top_employers.length, estimated);
  if (insights.length === 0) return null;

  return (
    <Card className="border-l-[3px]" style={{ borderLeftColor: "var(--content-ai)" }}>
      <CardHeader>
        <div className="flex items-center gap-2">
          <span
            className="flex size-7 items-center justify-center rounded-lg"
            style={{ background: "var(--content-ai-soft)" }}
          >
            <Sparkles className="size-4" strokeWidth={1.9} style={{ color: "var(--content-ai)" }} />
          </span>
          <CardTitle>{t("aiInsightsTitle")}</CardTitle>
        </div>
      </CardHeader>
      <CardContent>
        <p className="mb-2 type-caption text-muted-foreground">{t("aiInsightsDisclaimer")}</p>
        <ul className="space-y-2">
          {insights.map((key) => (
            <li key={key} className="flex items-start gap-2 text-[0.8125rem] text-foreground">
              <Lightbulb aria-hidden className="mt-0.5 size-3.5 shrink-0" strokeWidth={1.9} style={{ color: "var(--content-ai)" }} />
              {t(key)}
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}

/* -------------------------------------------------------------------------- */
/* Skeleton                                                                     */
/* -------------------------------------------------------------------------- */

function OutcomesSkeleton() {
  return (
    <div className="space-y-4">
      <div className="h-12 animate-skeleton rounded-xl bg-[var(--bg-muted)]" />
      <div className="grid grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="h-[86px] animate-skeleton rounded-xl bg-[var(--bg-muted)]" />
        ))}
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        <div className="h-64 animate-skeleton rounded-xl bg-[var(--bg-muted)]" />
        <div className="h-64 animate-skeleton rounded-xl bg-[var(--bg-muted)]" />
      </div>
      <div className="h-80 animate-skeleton rounded-xl bg-[var(--bg-muted)]" />
    </div>
  );
}
