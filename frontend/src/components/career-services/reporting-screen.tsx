"use client";

import * as React from "react";
import { useLocale, useTranslations } from "next-intl";
import { useQuery } from "@tanstack/react-query";
import {
  AlertTriangle,
  CalendarCheck,
  FileSearch,
  Users,
  ListChecks,
} from "lucide-react";
import {
  AttentionPanel,
  type AttentionItem,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  DonutChart,
  type DonutSlice,
  EmptyState,
  HorizontalBars,
  type HorizontalBarDatum,
  KpiRow,
  KpiTile,
} from "@/components/kit";
import { CareerServicesShell } from "./career-services-shell";
import { CareerServicesPermissionGate } from "./permission-gate";
import { useApiErrorMessage } from "@/lib/auth/use-api-error";
import {
  ApiError,
  careerServicesApi,
  type ReportingBucket,
} from "@/lib/api";

const nf = new Intl.NumberFormat();

/** Severity buckets carry semantic meaning — map to the fixed viz hues. */
const SEVERITY_COLOR: Record<string, string> = {
  low: "var(--viz-emerald)",
  medium: "var(--viz-amber)",
  high: "var(--viz-rose)",
};

function toBars(buckets: ReportingBucket[]): HorizontalBarDatum[] {
  return buckets.map((b) => ({ label: b.label, value: b.count }));
}

function ChartCard({
  title,
  buckets,
  emptyLabel,
  children,
}: {
  title: string;
  buckets: ReportingBucket[];
  emptyLabel: string;
  children?: React.ReactNode;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
      </CardHeader>
      <CardContent>
        {buckets.length === 0 || buckets.every((b) => b.count === 0) ? (
          <p className="type-small text-muted-foreground">{emptyLabel}</p>
        ) : (
          (children ?? (
            <HorizontalBars data={toBars(buckets)} formatValue={(v) => nf.format(v)} ariaLabel={title} />
          ))
        )}
      </CardContent>
    </Card>
  );
}

function ReportingSkeleton() {
  return (
    <div className="space-y-4">
      <KpiRow cols={4}>
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="h-[86px] animate-skeleton rounded-xl bg-[var(--bg-muted)]" />
        ))}
      </KpiRow>
      <div className="grid gap-4 lg:grid-cols-3">
        <div className="h-64 animate-skeleton rounded-xl bg-[var(--bg-muted)] lg:col-span-2" />
        <div className="h-64 animate-skeleton rounded-xl bg-[var(--bg-muted)]" />
      </div>
    </div>
  );
}

export function ReportingScreen() {
  const t = useTranslations("careerServices");
  const locale = useLocale();
  const getErrorMessage = useApiErrorMessage();

  const query = useQuery({
    queryKey: ["career-services", "reporting-summary", locale],
    queryFn: () => careerServicesApi.getReportingSummary(locale),
    retry: false,
  });

  const data = query.data;

  const upcomingAppointments = React.useMemo(() => {
    if (!data) return 0;
    return data.appointments_by_status
      .filter((b) => b.code === "requested" || b.code === "confirmed")
      .reduce((sum, b) => sum + b.count, 0);
  }, [data]);

  const severitySlices: DonutSlice[] = React.useMemo(
    () =>
      (data?.at_risk_by_severity ?? []).map((b) => ({
        label: b.label,
        value: b.count,
        color: SEVERITY_COLOR[b.code],
      })),
    [data],
  );

  const permissionState =
    query.isError && query.error instanceof ApiError ? (
      <CareerServicesPermissionGate error={query.error} bodyOverride={t("reporting.permissionBody")} />
    ) : null;

  const attentionItems: AttentionItem[] = data
    ? [
        {
          key: "atRisk",
          label: t("sections.atRisk"),
          href: "/university/career-services/at-risk",
          icon: AlertTriangle,
          tone: data.open_at_risk_flags > 0 ? "danger" : "neutral",
          count: data.open_at_risk_flags,
          meta: t("reporting.metaOpen"),
        },
        {
          key: "cvReview",
          label: t("sections.cvReview"),
          href: "/university/career-services/cv-review",
          icon: FileSearch,
          tone: data.open_cv_reviews > 0 ? "warning" : "neutral",
          count: data.open_cv_reviews,
          meta: t("reporting.metaOpen"),
        },
        {
          key: "appointments",
          label: t("sections.appointments"),
          href: "/university/career-services/appointments",
          icon: CalendarCheck,
          tone: upcomingAppointments > 0 ? "info" : "neutral",
          count: upcomingAppointments,
          meta: t("reporting.metaUpcoming"),
        },
        {
          key: "cohorts",
          label: t("sections.cohorts"),
          href: "/university/career-services/cohorts",
          icon: Users,
          tone: "neutral",
          count: data.active_cohorts,
          meta: t("reporting.metaActive"),
        },
      ]
    : [];

  const isEmpty =
    data != null &&
    data.active_cohorts === 0 &&
    data.open_at_risk_flags === 0 &&
    data.open_cv_reviews === 0 &&
    upcomingAppointments === 0;

  return (
    <CareerServicesShell title={t("reporting.title")} description={t("reporting.subtitle")}>
      {permissionState ??
        (query.isPending ? (
          <ReportingSkeleton />
        ) : query.isError ? (
          <EmptyState kind="error" title={t("reporting.loadFailed")} description={getErrorMessage(query.error)} />
        ) : isEmpty ? (
          <EmptyState
            kind="empty"
            icon={ListChecks}
            title={t("reporting.emptyTitle")}
            description={t("reporting.emptyBody")}
          />
        ) : (
          <div className="space-y-4">
            <KpiRow cols={4}>
              <KpiTile
                label={t("reporting.kpiOpenAtRisk")}
                value={nf.format(data!.open_at_risk_flags)}
                icon={AlertTriangle}
                href="/university/career-services/at-risk"
              />
              <KpiTile
                label={t("reporting.kpiOpenCvReviews")}
                value={nf.format(data!.open_cv_reviews)}
                icon={FileSearch}
                href="/university/career-services/cv-review"
              />
              <KpiTile
                label={t("reporting.kpiUpcomingAppointments")}
                value={nf.format(upcomingAppointments)}
                icon={CalendarCheck}
                href="/university/career-services/appointments"
              />
              <KpiTile
                label={t("reporting.kpiActiveCohorts")}
                value={nf.format(data!.active_cohorts)}
                icon={Users}
                href="/university/career-services/cohorts"
              />
            </KpiRow>

            <div className="grid gap-4 lg:grid-cols-3">
              <Card className="lg:col-span-2">
                <CardHeader>
                  <CardTitle>{t("reporting.atRiskBreakdownTitle")}</CardTitle>
                </CardHeader>
                <CardContent>
                  {severitySlices.every((s) => s.value === 0) &&
                  data!.at_risk_by_status.every((b) => b.count === 0) ? (
                    <p className="type-small text-muted-foreground">{t("reporting.noData")}</p>
                  ) : (
                    <div className="grid gap-6 sm:grid-cols-2">
                      <div>
                        <p className="mb-2 type-caption font-semibold uppercase tracking-wide text-muted-foreground">
                          {t("reporting.atRiskBySeverity")}
                        </p>
                        <DonutChart
                          data={severitySlices}
                          centerValue={nf.format(data!.open_at_risk_flags)}
                          centerLabel={t("reporting.metaOpen")}
                          formatValue={(v) => nf.format(v)}
                          ariaLabel={t("reporting.atRiskBySeverity")}
                        />
                      </div>
                      <div>
                        <p className="mb-2 type-caption font-semibold uppercase tracking-wide text-muted-foreground">
                          {t("reporting.atRiskByStatus")}
                        </p>
                        <HorizontalBars
                          data={toBars(data!.at_risk_by_status)}
                          formatValue={(v) => nf.format(v)}
                          ariaLabel={t("reporting.atRiskByStatus")}
                        />
                      </div>
                    </div>
                  )}
                </CardContent>
              </Card>

              <Card>
                <CardHeader>
                  <CardTitle>{t("reporting.jumpToTitle")}</CardTitle>
                </CardHeader>
                <CardContent>
                  <AttentionPanel items={attentionItems} />
                </CardContent>
              </Card>
            </div>

            <div className="grid gap-4 lg:grid-cols-3">
              <ChartCard
                title={t("reporting.cvReviewByStatus")}
                buckets={data!.cv_review_by_status}
                emptyLabel={t("reporting.noData")}
              />
              <ChartCard
                title={t("reporting.appointmentsByStatus")}
                buckets={data!.appointments_by_status}
                emptyLabel={t("reporting.noData")}
              />
              <ChartCard
                title={t("reporting.interventionsByOutcome")}
                buckets={data!.interventions_by_outcome}
                emptyLabel={t("reporting.noData")}
              />
            </div>
          </div>
        ))}
    </CareerServicesShell>
  );
}
