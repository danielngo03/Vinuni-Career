"use client";

import * as React from "react";
import { useLocale, useTranslations } from "next-intl";
import { useQuery } from "@tanstack/react-query";
import {
  Activity,
  BarChart3,
  Building2,
  Briefcase,
  FileCheck2,
  FileText,
  Gauge,
  Gavel,
  Handshake,
  HeartPulse,
  Layers,
  Minus,
  ShieldAlert,
  TrendingDown,
  TrendingUp,
} from "lucide-react";
import { Link } from "@/i18n/navigation";
import { Button } from "@/components/ui";
import {
  ActivityFeed,
  type ActivityEntry,
  AreaChart,
  AttentionPanel,
  type AttentionItem,
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
  GradientHeroCard,
  HorizontalBars,
  type HorizontalBarDatum,
  KpiRow,
  KpiTile,
  StatusChip,
  type ChipTone,
} from "@/components/kit";
import { PageHeader } from "@/components/layout/page-header";
import { formatDateTime, formatRelativeTime } from "@/lib/format";
import {
  ApiError,
  careerServicesApi,
  dashboardsApi,
  type CareerServicesReportingSummary,
  type UniversityDashboard as UniversityDashboardData,
  type UniversityMarketIntelligence,
  type UniversityPlatformStats,
} from "@/lib/api";
import { useAuthStore } from "@/stores/auth-store";
import { DashboardGuestGate } from "./dashboard-kit";

const nf = new Intl.NumberFormat();

/* -------------------------------------------------------------------------- */
/* Skeleton                                                                    */
/* -------------------------------------------------------------------------- */

function CommandCenterSkeleton() {
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 sm:gap-4 lg:grid-cols-5">
        {Array.from({ length: 5 }).map((_, i) => (
          <div key={i} className="h-[86px] animate-skeleton rounded-xl bg-[var(--bg-muted)]" />
        ))}
      </div>
      <div className="grid gap-4 lg:grid-cols-3">
        <div className="h-44 animate-skeleton rounded-xl bg-[var(--bg-muted)] lg:col-span-2" />
        <div className="h-44 animate-skeleton rounded-xl bg-[var(--bg-muted)]" />
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        <div className="h-64 animate-skeleton rounded-xl bg-[var(--bg-muted)]" />
        <div className="h-64 animate-skeleton rounded-xl bg-[var(--bg-muted)]" />
      </div>
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* Screen                                                                      */
/* -------------------------------------------------------------------------- */

/**
 * University command center (v10). Wires the real university operations,
 * platform-reports, market-intelligence, and (optionally, permission-gated)
 * career-services reads into the locked kit: KPI row → governance-load hero +
 * review-load donut → applications trend + hiring-market snapshot → moderation
 * queue + partner requests → a "needs review" attention queue + career-services
 * health + recent submissions. Every widget degrades honestly (loading / empty /
 * permission-locked) and never fabricates a number. Mirrors the partner command
 * center exemplar so the two operating shells read as one product.
 */
export function UniversityDashboard() {
  const t = useTranslations("universityDashboard");
  const tStates = useTranslations("states");
  const tc = useTranslations("common");
  const locale = useLocale();
  const authed = useAuthStore((s) => s.status === "authenticated");

  const dashQ = useQuery({
    queryKey: ["dashboard", "university", "ops"],
    queryFn: () => dashboardsApi.university(),
    enabled: authed,
    retry: false,
  });
  const reportsQ = useQuery({
    queryKey: ["dashboard", "university", "reports"],
    queryFn: () => dashboardsApi.universityReports(),
    enabled: authed,
    retry: false,
  });
  const marketQ = useQuery({
    queryKey: ["dashboard", "university", "market-intelligence"],
    queryFn: () => dashboardsApi.marketIntelligence(),
    enabled: authed,
    retry: false,
  });
  // Career-services reporting is a SEPARATE per-resource permission gate — a
  // university admin may or may not hold it. Never let its 403 break the page.
  const careQ = useQuery({
    queryKey: ["dashboard", "university", "career-services-summary", locale],
    queryFn: () => careerServicesApi.getReportingSummary(locale),
    enabled: authed,
    retry: false,
  });

  const offline = dashQ.error instanceof ApiError && dashQ.error.code === "NETWORK_ERROR";
  const permission = dashQ.error instanceof ApiError && dashQ.error.isPermissionError;

  const header = (
    <PageHeader
      title={t("title")}
      subtitle={t("subtitle")}
      meta={
        marketQ.data ? (
          <span className="inline-flex items-center gap-1.5">
            <Activity className="size-3.5" strokeWidth={1.8} />
            {t("metaUpdated", { time: formatRelativeTime(marketQ.data.computed_at, locale) })}
          </span>
        ) : undefined
      }
      actions={
        <Link href="/university/reports">
          <Button variant="secondary" size="sm">
            <BarChart3 className="size-4" strokeWidth={1.8} />
            {t("viewReports")}
          </Button>
        </Link>
      }
    />
  );

  if (!authed) {
    return (
      <>
        {header}
        <DashboardGuestGate persona="university" />
      </>
    );
  }
  if (dashQ.isPending) {
    return (
      <>
        {header}
        <CommandCenterSkeleton />
      </>
    );
  }
  if (dashQ.isError) {
    if (permission) {
      return (
        <>
          {header}
          <EmptyState
            kind="permission"
            title={tStates("permissionTitle")}
            description={tStates("permissionBody")}
          />
        </>
      );
    }
    return (
      <>
        {header}
        <EmptyState
          kind={offline ? "offline" : "error"}
          title={offline ? tStates("offlineTitle") : tStates("errorTitle")}
          description={offline ? tStates("offlineBody") : tStates("errorBody")}
          action={
            <Button variant="secondary" onClick={() => dashQ.refetch()}>
              {tc("retry")}
            </Button>
          }
        />
      </>
    );
  }

  const data = dashQ.data;
  const care = careQ.data;
  const careLocked = careQ.isError;

  return (
    <>
      {header}
      <div className="space-y-4">
        <KpiSection data={data} care={care} careLocked={careLocked} />

        {/* Governance load hero + review-load donut */}
        <div className="grid gap-4 lg:grid-cols-3">
          <HeroSection data={data} care={care} className="lg:col-span-2" />
          <ReviewLoadCard data={data} care={care} loading={careQ.isPending} />
        </div>

        {/* Applications trend + hiring market */}
        <div className="grid gap-4 lg:grid-cols-2">
          <TrendCard reports={reportsQ.data} loading={reportsQ.isPending} />
          <MarketCard market={marketQ.data} loading={marketQ.isPending} />
        </div>

        {/* Queues + rail */}
        <div className="grid gap-4 lg:grid-cols-3">
          <div className="space-y-4 lg:col-span-2">
            <ModerationQueueCard data={data} locale={locale} />
            <PartnerRequestsCard data={data} locale={locale} />
          </div>
          <div className="space-y-4">
            <AttentionCard data={data} care={care} />
            <CareerServicesCard care={care} locked={careLocked} loading={careQ.isPending} />
            <RecentActivityCard data={data} locale={locale} />
          </div>
        </div>
      </div>
    </>
  );
}

/* -------------------------------------------------------------------------- */
/* Governance helpers                                                          */
/* -------------------------------------------------------------------------- */

interface GovernanceLoad {
  moderation: number;
  partners: number;
  cvReviews: number;
  atRisk: number;
  careAvailable: boolean;
  total: number;
  status: "onTrack" | "building" | "overloaded";
}

function computeLoad(
  data: UniversityDashboardData,
  care: CareerServicesReportingSummary | undefined,
): GovernanceLoad {
  const moderation = data.metrics.jobs_pending_moderation;
  const partners = data.metrics.partners_pending;
  const cvReviews = care?.open_cv_reviews ?? 0;
  const atRisk = care?.open_at_risk_flags ?? 0;
  const total = moderation + partners + cvReviews + atRisk;
  const status = total <= 3 ? "onTrack" : total <= 10 ? "building" : "overloaded";
  return { moderation, partners, cvReviews, atRisk, careAvailable: !!care, total, status };
}

/* -------------------------------------------------------------------------- */
/* KPI row                                                                     */
/* -------------------------------------------------------------------------- */

function KpiSection({
  data,
  care,
  careLocked,
}: {
  data: UniversityDashboardData;
  care: CareerServicesReportingSummary | undefined;
  careLocked: boolean;
}) {
  const t = useTranslations("universityDashboard");
  const m = data.metrics;

  return (
    <KpiRow cols={5}>
      <KpiTile
        label={t("kpi.pendingApprovals")}
        value={nf.format(m.partners_pending)}
        icon={Handshake}
        hint={m.partners_pending > 0 ? t("kpi.pendingApprovalsHint", { count: m.partners_pending }) : undefined}
        href="/university/partners"
      />
      <KpiTile
        label={t("kpi.moderationQueue")}
        value={nf.format(m.jobs_pending_moderation)}
        icon={Gavel}
        hint={m.jobs_pending_moderation > 0 ? t("kpi.moderationQueueHint", { count: m.jobs_pending_moderation }) : undefined}
        href="/university/moderation/jobs"
      />
      <KpiTile
        label={t("kpi.atRisk")}
        value={care ? nf.format(care.open_at_risk_flags) : "—"}
        icon={ShieldAlert}
        hint={careLocked ? t("kpi.atRiskLocked") : t("kpi.atRiskHint")}
        href={care ? "/university/career-services/at-risk" : undefined}
      />
      <KpiTile
        label={t("kpi.activePartners")}
        value={nf.format(m.partners_active)}
        icon={Building2}
        href="/university/partners"
      />
      <KpiTile
        label={t("kpi.activeJobs")}
        value={nf.format(m.jobs_active_total)}
        icon={Briefcase}
        href="/university/reports"
      />
    </KpiRow>
  );
}

/* -------------------------------------------------------------------------- */
/* Hero — governance load                                                      */
/* -------------------------------------------------------------------------- */

function HeroSection({
  data,
  care,
  className,
}: {
  data: UniversityDashboardData;
  care: CareerServicesReportingSummary | undefined;
  className?: string;
}) {
  const t = useTranslations("universityDashboard");
  const load = computeLoad(data, care);
  const caption = load.careAvailable
    ? t("hero.captionWithCare", {
        moderation: load.moderation,
        partners: load.partners,
        care: load.cvReviews + load.atRisk,
      })
    : t("hero.caption", { moderation: load.moderation, partners: load.partners });

  const statusLabel =
    load.status === "onTrack"
      ? t("hero.statusOnTrack")
      : load.status === "building"
        ? t("hero.statusBuilding")
        : t("hero.statusOverloaded");

  return (
    <GradientHeroCard
      className={className}
      eyebrow={t("hero.eyebrow")}
      icon={Layers}
      title={t("hero.title")}
      value={nf.format(load.total)}
      caption={caption}
      footer={
        <>
          <span className="inline-flex items-center gap-1.5 rounded-full bg-white/20 px-2.5 py-1 text-xs font-semibold text-white">
            {statusLabel}
          </span>
          {load.moderation > 0 && (
            <span className="inline-flex items-center gap-1.5 rounded-full bg-white/15 px-2.5 py-1 text-xs font-semibold text-white">
              <Gavel className="size-3.5" strokeWidth={2} />
              {t("hero.chipModeration", { count: load.moderation })}
            </span>
          )}
          {load.partners > 0 && (
            <span className="inline-flex items-center gap-1.5 rounded-full bg-white/15 px-2.5 py-1 text-xs font-semibold text-white">
              <Handshake className="size-3.5" strokeWidth={2} />
              {t("hero.chipPartners", { count: load.partners })}
            </span>
          )}
          {load.careAvailable && load.cvReviews + load.atRisk > 0 && (
            <span className="inline-flex items-center gap-1.5 rounded-full bg-white/15 px-2.5 py-1 text-xs font-semibold text-white">
              <HeartPulse className="size-3.5" strokeWidth={2} />
              {t("hero.chipCare", { count: load.cvReviews + load.atRisk })}
            </span>
          )}
        </>
      }
    />
  );
}

/* -------------------------------------------------------------------------- */
/* Review-load donut                                                           */
/* -------------------------------------------------------------------------- */

function ReviewLoadCard({
  data,
  care,
  loading,
}: {
  data: UniversityDashboardData;
  care: CareerServicesReportingSummary | undefined;
  loading: boolean;
}) {
  const t = useTranslations("universityDashboard");
  const load = computeLoad(data, care);

  const rows: { label: string; value: number; tone: ChipTone; color: string }[] = [
    { label: t("reviewLoad.moderation"), value: load.moderation, tone: "warning", color: "var(--content-warning)" },
    { label: t("reviewLoad.partners"), value: load.partners, tone: "info", color: "var(--content-info)" },
  ];
  if (load.careAvailable) {
    rows.push(
      { label: t("reviewLoad.cvReviews"), value: load.cvReviews, tone: "teal", color: "var(--viz-teal)" },
      { label: t("reviewLoad.atRisk"), value: load.atRisk, tone: "danger", color: "var(--content-danger)" },
    );
  }

  return (
    <Card>
      <CardHeader>
        <div>
          <CardTitle>{t("reviewLoad.title")}</CardTitle>
        </div>
        <CardToolbar>
          <Gauge className="size-4 text-muted-foreground" strokeWidth={1.8} />
        </CardToolbar>
      </CardHeader>
      <CardContent>
        {loading ? (
          <div className="h-[200px] animate-skeleton rounded-lg bg-[var(--bg-muted)]" />
        ) : load.total === 0 ? (
          <EmptyState kind="empty" title={t("reviewLoad.emptyTitle")} description={t("reviewLoad.emptyBody")} />
        ) : (
          <>
            <DonutChart
              data={rows.filter((r) => r.value > 0).map((r) => ({ label: r.label, value: r.value, color: r.color }))}
              centerValue={nf.format(load.total)}
              centerLabel={t("reviewLoad.center")}
              formatValue={(v) => nf.format(v)}
            />
            <ul className="mt-3 space-y-1.5">
              {rows.map((r) => (
                <li key={r.label} className="flex items-center justify-between text-[0.8125rem]">
                  <StatusChip tone={r.tone} dot size="sm">
                    {r.label}
                  </StatusChip>
                  <span className="font-semibold tabular-nums text-foreground">{nf.format(r.value)}</span>
                </li>
              ))}
            </ul>
          </>
        )}
      </CardContent>
    </Card>
  );
}

/* -------------------------------------------------------------------------- */
/* Applications trend                                                          */
/* -------------------------------------------------------------------------- */

function TrendCard({
  reports,
  loading,
}: {
  reports: UniversityPlatformStats | undefined;
  loading: boolean;
}) {
  const t = useTranslations("universityDashboard");
  const monthly = reports?.monthly_applications ?? [];

  return (
    <Card>
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
        {loading ? (
          <div className="h-[220px] animate-skeleton rounded-lg bg-[var(--bg-muted)]" />
        ) : monthly.length === 0 ? (
          <EmptyState kind="empty" title={t("trend.emptyTitle")} description={t("trend.emptyBody")} />
        ) : (
          <AreaChart
            data={monthly.map((p) => ({ month: p.label, count: p.count }))}
            xKey="month"
            series={[{ key: "count", label: t("trend.series"), color: "var(--viz-indigo)" }]}
            height={220}
            formatValue={(v) => nf.format(v)}
            ariaLabel={t("trend.title")}
          />
        )}
      </CardContent>
    </Card>
  );
}

/* -------------------------------------------------------------------------- */
/* Hiring market snapshot                                                       */
/* -------------------------------------------------------------------------- */

function MarketCard({
  market,
  loading,
}: {
  market: UniversityMarketIntelligence | undefined;
  loading: boolean;
}) {
  const t = useTranslations("universityDashboard");
  const skills = React.useMemo<HorizontalBarDatum[]>(
    () => (market?.top_skills ?? []).slice(0, 6).map((s) => ({ label: s.skill, value: s.count })),
    [market],
  );

  const TrendIcon =
    market?.trend === "up" ? TrendingUp : market?.trend === "down" ? TrendingDown : Minus;
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
          <Link href="/university/reports" className="text-[0.8125rem] font-semibold text-[var(--brand-primary)] hover:underline">
            {t("market.viewReports")}
          </Link>
        </CardToolbar>
      </CardHeader>
      <CardContent>
        {loading ? (
          <div className="h-[220px] animate-skeleton rounded-lg bg-[var(--bg-muted)]" />
        ) : !market || market.active_jobs === 0 ? (
          <EmptyState kind="empty" title={t("market.emptyTitle")} description={t("market.emptyBody")} />
        ) : (
          <div className="space-y-4">
            <div className="flex items-end justify-between gap-3">
              <div>
                <p className="type-caption text-muted-foreground">{t("market.activeJobs")}</p>
                <p className="type-metric text-foreground">{nf.format(market.active_jobs)}</p>
                <p className="type-caption mt-0.5 text-muted-foreground">
                  {t("market.trend30d", { count: market.jobs_last_30d })}
                </p>
              </div>
              <span
                className="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[0.6875rem] font-semibold"
                style={{ background: "var(--bg-muted)", color: trendColor }}
              >
                <TrendIcon aria-hidden className="size-3" strokeWidth={2.2} />
                {trendLabel}
              </span>
            </div>
            {market.low_signal ? (
              <p className="rounded-lg bg-[var(--bg-subtle)] px-3 py-2 type-small text-muted-foreground">
                {t("market.lowSignal")}
              </p>
            ) : skills.length > 0 ? (
              <div>
                <p className="type-caption mb-2 font-semibold uppercase tracking-[0.06em] text-muted-foreground">
                  {t("market.topSkills")}
                </p>
                <HorizontalBars data={skills} formatValue={(v) => nf.format(v)} ariaLabel={t("market.topSkills")} />
              </div>
            ) : null}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

/* -------------------------------------------------------------------------- */
/* Moderation queue table                                                      */
/* -------------------------------------------------------------------------- */

type ModItem = UniversityDashboardData["moderation_queue_recent"][number];

function ModerationQueueCard({ data, locale }: { data: UniversityDashboardData; locale: string }) {
  const t = useTranslations("universityDashboard");
  const cols: ColumnDef<ModItem, unknown>[] = [
    {
      accessorKey: "title",
      header: t("moderationQueue.colJob"),
      cell: ({ row }) => (
        <Link
          href="/university/moderation/jobs"
          className="font-semibold text-foreground hover:text-[var(--brand-primary)]"
        >
          {row.original.title}
        </Link>
      ),
    },
    {
      accessorKey: "company_name",
      header: t("moderationQueue.colEmployer"),
      cell: ({ row }) => (
        <span className="text-muted-foreground">
          {row.original.company_name ?? t("moderationQueue.unknownCompany")}
        </span>
      ),
    },
    {
      accessorKey: "submitted_at",
      header: t("moderationQueue.colSubmitted"),
      meta: { align: "right" },
      cell: ({ row }) => (
        <span className="tabular-nums text-muted-foreground">
          {formatDateTime(row.original.submitted_at, locale)}
        </span>
      ),
    },
  ];

  return (
    <Card>
      <CardHeader>
        <div>
          <CardTitle>{t("moderationQueue.title")}</CardTitle>
        </div>
        <CardToolbar>
          <Link href="/university/moderation/jobs" className="text-[0.8125rem] font-semibold text-[var(--brand-primary)] hover:underline">
            {t("moderationQueue.openQueue")}
          </Link>
        </CardToolbar>
      </CardHeader>
      <CardContent>
        <DataTable
          columns={cols}
          data={data.moderation_queue_recent}
          getRowId={(r) => r.id}
          pageSize={6}
          empty={<EmptyState kind="empty" title={t("moderationQueue.emptyTitle")} description={t("moderationQueue.emptyBody")} />}
        />
      </CardContent>
    </Card>
  );
}

/* -------------------------------------------------------------------------- */
/* Partner requests                                                            */
/* -------------------------------------------------------------------------- */

function PartnerRequestsCard({ data, locale }: { data: UniversityDashboardData; locale: string }) {
  const t = useTranslations("universityDashboard");
  const items = data.partner_requests_recent;

  return (
    <Card>
      <CardHeader>
        <div>
          <CardTitle>{t("partnerRequests.title")}</CardTitle>
        </div>
        <CardToolbar>
          <Link href="/university/partners" className="text-[0.8125rem] font-semibold text-[var(--brand-primary)] hover:underline">
            {t("partnerRequests.openPartners")}
          </Link>
        </CardToolbar>
      </CardHeader>
      <CardContent>
        {items.length === 0 ? (
          <EmptyState kind="empty" title={t("partnerRequests.emptyTitle")} description={t("partnerRequests.emptyBody")} />
        ) : (
          <ul className="divide-y divide-border overflow-hidden rounded-xl border border-border">
            {items.map((item) => (
              <li key={item.id}>
                <Link
                  href="/university/partners"
                  className="group flex items-center gap-3 px-4 py-3 outline-none transition-colors hover:bg-[var(--bg-subtle)] focus-visible:bg-[var(--bg-subtle)]"
                >
                  <span
                    className="flex size-8 shrink-0 items-center justify-center rounded-lg"
                    style={{ background: "var(--content-info-soft)" }}
                  >
                    <Handshake className="size-4" strokeWidth={1.9} style={{ color: "var(--content-info)" }} />
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-[0.8125rem] font-semibold text-foreground group-hover:text-[var(--brand-primary)]">
                      {item.company_name ?? t("partnerRequests.unknownCompany")}
                    </span>
                    <span className="mt-0.5 block truncate type-caption text-muted-foreground">
                      {t("partnerRequests.requestedOn", { date: formatDateTime(item.submitted_at, locale) })}
                    </span>
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}

/* -------------------------------------------------------------------------- */
/* Attention — needs review                                                    */
/* -------------------------------------------------------------------------- */

function AttentionCard({
  data,
  care,
}: {
  data: UniversityDashboardData;
  care: CareerServicesReportingSummary | undefined;
}) {
  const t = useTranslations("universityDashboard");
  const m = data.metrics;

  const items: AttentionItem[] = [];
  if (m.jobs_pending_moderation > 0) {
    items.push({
      key: "moderation",
      label: t("attention.moderation"),
      href: "/university/moderation/jobs",
      icon: Gavel,
      tone: "warning",
      count: m.jobs_pending_moderation,
      meta: m.jobs_pending_moderation > 8 ? t("attention.priorityHigh") : t("attention.priorityMedium"),
    });
  }
  if (m.partners_pending > 0) {
    items.push({
      key: "partners",
      label: t("attention.partners"),
      href: "/university/partners",
      icon: Handshake,
      tone: "info",
      count: m.partners_pending,
      meta: t("attention.priorityMedium"),
    });
  }
  if (care && care.open_at_risk_flags > 0) {
    items.push({
      key: "at_risk",
      label: t("attention.atRisk"),
      href: "/university/career-services/at-risk",
      icon: ShieldAlert,
      tone: "danger",
      count: care.open_at_risk_flags,
      meta: t("attention.priorityHigh"),
    });
  }
  if (care && care.open_cv_reviews > 0) {
    items.push({
      key: "cv_reviews",
      label: t("attention.cvReviews"),
      href: "/university/career-services/cv-review",
      icon: FileCheck2,
      tone: "teal",
      count: care.open_cv_reviews,
      meta: t("attention.priorityLow"),
    });
  }

  return (
    <Card>
      <CardHeader>
        <div>
          <CardTitle>{t("attention.title")}</CardTitle>
        </div>
        <CardToolbar>
          <span className="inline-flex min-w-6 items-center justify-center rounded-full bg-[var(--bg-muted)] px-2 py-0.5 text-xs font-bold tabular-nums text-muted-foreground">
            {items.length}
          </span>
        </CardToolbar>
      </CardHeader>
      <CardContent>
        <AttentionPanel
          items={items}
          empty={<EmptyState kind="empty" title={t("attention.emptyTitle")} description={t("attention.emptyBody")} />}
        />
      </CardContent>
    </Card>
  );
}

/* -------------------------------------------------------------------------- */
/* Career-services health                                                       */
/* -------------------------------------------------------------------------- */

function CareerServicesCard({
  care,
  locked,
  loading,
}: {
  care: CareerServicesReportingSummary | undefined;
  locked: boolean;
  loading: boolean;
}) {
  const t = useTranslations("universityDashboard");
  const severity = React.useMemo<HorizontalBarDatum[]>(() => {
    if (!care) return [];
    return care.at_risk_by_severity
      .filter((b) => b.count > 0)
      .map((b) => ({ label: b.label, value: b.count }));
  }, [care]);

  const stats: [string, number][] = care
    ? [
        [t("careerServices.atRiskOpen"), care.open_at_risk_flags],
        [t("careerServices.cvReviewsOpen"), care.open_cv_reviews],
        [t("careerServices.activeCohorts"), care.active_cohorts],
      ]
    : [];
  const empty = care != null && care.open_at_risk_flags + care.open_cv_reviews + care.active_cohorts === 0;

  return (
    <Card>
      <CardHeader>
        <div>
          <CardTitle>{t("careerServices.title")}</CardTitle>
          <CardDescription>{t("careerServices.subtitle")}</CardDescription>
        </div>
        <CardToolbar>
          <HeartPulse className="size-4 text-muted-foreground" strokeWidth={1.8} />
        </CardToolbar>
      </CardHeader>
      <CardContent>
        {locked ? (
          <EmptyState kind="permission" title={t("careerServices.lockedTitle")} description={t("careerServices.lockedBody")} />
        ) : loading ? (
          <div className="h-32 animate-skeleton rounded-lg bg-[var(--bg-muted)]" />
        ) : empty || !care ? (
          <EmptyState kind="empty" title={t("careerServices.emptyTitle")} description={t("careerServices.emptyBody")} />
        ) : (
          <div className="space-y-3">
            <dl className="grid grid-cols-3 gap-2.5">
              {stats.map(([label, value]) => (
                <div key={label} className="rounded-lg border border-border bg-[var(--bg-subtle)] px-3 py-2">
                  <dd className="text-base font-bold tabular-nums text-foreground">{nf.format(value)}</dd>
                  <dt className="type-caption mt-0.5 text-muted-foreground">{label}</dt>
                </div>
              ))}
            </dl>
            {severity.length > 0 && (
              <div>
                <p className="type-caption mb-2 font-semibold uppercase tracking-[0.06em] text-muted-foreground">
                  {t("careerServices.bySeverity")}
                </p>
                <HorizontalBars
                  data={severity}
                  formatValue={(v) => nf.format(v)}
                  ariaLabel={t("careerServices.bySeverity")}
                />
              </div>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

/* -------------------------------------------------------------------------- */
/* Recent submissions                                                          */
/* -------------------------------------------------------------------------- */

function RecentActivityCard({ data, locale }: { data: UniversityDashboardData; locale: string }) {
  const t = useTranslations("universityDashboard");
  const items = React.useMemo<ActivityEntry[]>(() => {
    const merged: { key: string; at: string; title: React.ReactNode; icon: React.ElementType; tone: ChipTone; meta: string }[] = [];
    for (const j of data.moderation_queue_recent) {
      merged.push({
        key: `mod-${j.id}`,
        at: j.submitted_at,
        icon: Gavel,
        tone: "warning",
        title: (
          <span>
            {t("activity.moderationEvent")} · <span className="font-semibold">{j.title}</span>
          </span>
        ),
        meta: `${j.company_name ?? t("moderationQueue.unknownCompany")} · ${formatRelativeTime(j.submitted_at, locale)}`,
      });
    }
    for (const p of data.partner_requests_recent) {
      merged.push({
        key: `partner-${p.id}`,
        at: p.submitted_at,
        icon: Handshake,
        tone: "info",
        title: (
          <span>
            {t("activity.partnerEvent")} · <span className="font-semibold">{p.company_name ?? t("partnerRequests.unknownCompany")}</span>
          </span>
        ),
        meta: formatRelativeTime(p.submitted_at, locale),
      });
    }
    return merged
      .sort((a, b) => new Date(b.at).getTime() - new Date(a.at).getTime())
      .slice(0, 6)
      .map((e) => ({ key: e.key, icon: e.icon, tone: e.tone, title: e.title, meta: e.meta }));
  }, [data, locale, t]);

  return (
    <Card>
      <CardHeader>
        <div>
          <CardTitle>{t("activity.title")}</CardTitle>
        </div>
        <CardToolbar>
          <FileText className="size-4 text-muted-foreground" strokeWidth={1.8} />
        </CardToolbar>
      </CardHeader>
      <CardContent>
        <ActivityFeed
          items={items}
          empty={<EmptyState kind="empty" title={t("activity.emptyTitle")} description={t("activity.emptyBody")} />}
        />
      </CardContent>
    </Card>
  );
}
