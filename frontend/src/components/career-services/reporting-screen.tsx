"use client";

import { useLocale, useTranslations } from "next-intl";
import { useQuery } from "@tanstack/react-query";
import {
  ChartBar,
  FileMagnifyingGlass,
  Flag,
  UsersThree,
} from "@phosphor-icons/react";
import { EmptyState } from "@/components/ui";
import { CareerServicesShell } from "./career-services-shell";
import { CareerServicesPermissionGate } from "./permission-gate";
import { useApiErrorMessage } from "@/lib/auth/use-api-error";
import { ApiError, careerServicesApi, type ReportingBucket } from "@/lib/api";

function StatCard({
  label,
  value,
  loading,
  icon,
  iconBg = "icon-chip-primary",
}: {
  label: string;
  value: string;
  loading: boolean;
  icon: React.ReactNode;
  iconBg?: string;
}) {
  return (
    <div className="rounded-2xl border border-white/60 bg-white/85 px-5 py-4 shadow-[0_2px_16px_rgba(11,34,57,0.06)] backdrop-blur-xl">
      <div className={`mb-3 flex size-11 items-center justify-center rounded-xl shadow-sm ${iconBg}`}>
        {icon}
      </div>
      <p className="text-3xl font-black tracking-tight text-[var(--text-primary)]">
        {loading ? "…" : value}
      </p>
      <p className="mt-1 text-xs font-medium text-[var(--text-secondary)]">{label}</p>
    </div>
  );
}

function BucketList({ title, buckets }: { title: string; buckets: ReportingBucket[] }) {
  const t = useTranslations("careerServices");
  return (
    <section className="rounded-2xl border border-white/60 bg-white/82 p-4 backdrop-blur-md">
      <h2 className="mb-3 text-sm font-semibold text-[var(--text-primary)]">{title}</h2>
      {buckets.length === 0 ? (
        <p className="text-sm text-[var(--text-muted)]">{t("reporting.noData")}</p>
      ) : (
        <ul className="space-y-2">
          {buckets.map((b) => (
            <li key={b.code} className="flex items-center justify-between gap-3 text-sm">
              <span className="truncate text-[var(--text-secondary)]">{b.label}</span>
              <span className="shrink-0 font-semibold text-[var(--text-primary)]">{b.count}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
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

  const permissionState =
    query.isError && query.error instanceof ApiError ? (
      <CareerServicesPermissionGate error={query.error} bodyOverride={t("reporting.permissionBody")} />
    ) : null;

  const data = query.data;
  const loading = query.isPending;

  return (
    <CareerServicesShell title={t("reporting.title")} description={t("reporting.subtitle")}>
      {permissionState ?? (
        <>
          {query.isError ? (
            <EmptyState kind="error" title={t("reporting.loadFailed")} description={getErrorMessage(query.error)} />
          ) : (
            <>
              <div className="mb-5 grid grid-cols-1 gap-3 sm:grid-cols-3">
                <StatCard
                  label={t("reporting.kpiActiveCohorts")}
                  value={data ? String(data.active_cohorts) : "—"}
                  loading={loading}
                  icon={<UsersThree aria-hidden weight="duotone" className="size-5 text-white" />}
                  iconBg="icon-chip-primary"
                />
                <StatCard
                  label={t("reporting.kpiOpenAtRisk")}
                  value={data ? String(data.open_at_risk_flags) : "—"}
                  loading={loading}
                  icon={<Flag aria-hidden weight="duotone" className="size-5 text-white" />}
                  iconBg="icon-chip-warning"
                />
                <StatCard
                  label={t("reporting.kpiOpenCvReviews")}
                  value={data ? String(data.open_cv_reviews) : "—"}
                  loading={loading}
                  icon={<FileMagnifyingGlass aria-hidden weight="duotone" className="size-5 text-white" />}
                  iconBg="icon-chip-info"
                />
              </div>

              <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
                <BucketList title={t("reporting.atRiskByStatus")} buckets={data?.at_risk_by_status ?? []} />
                <BucketList title={t("reporting.atRiskBySeverity")} buckets={data?.at_risk_by_severity ?? []} />
                <BucketList title={t("reporting.cvReviewByStatus")} buckets={data?.cv_review_by_status ?? []} />
                <BucketList
                  title={t("reporting.appointmentsByStatus")}
                  buckets={data?.appointments_by_status ?? []}
                />
                <BucketList
                  title={t("reporting.interventionsByOutcome")}
                  buckets={data?.interventions_by_outcome ?? []}
                />
              </div>

              {data &&
                data.active_cohorts === 0 &&
                data.open_at_risk_flags === 0 &&
                data.open_cv_reviews === 0 && (
                  <EmptyState
                    kind="empty"
                    icon={ChartBar}
                    title={t("reporting.emptyTitle")}
                    description={t("reporting.emptyBody")}
                    className="mt-4"
                  />
                )}
            </>
          )}
        </>
      )}
    </CareerServicesShell>
  );
}
