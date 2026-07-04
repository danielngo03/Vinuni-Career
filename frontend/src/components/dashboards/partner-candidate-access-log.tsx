"use client";

import { useLocale, useTranslations } from "next-intl";
import { useQuery } from "@tanstack/react-query";
import { Lock, ShieldCheck } from "@phosphor-icons/react";
import { Link } from "@/i18n/navigation";
import { Button, DataTable, EmptyState } from "@/components/ui";
import type { Column } from "@/components/ui";
import { PageHeader } from "@/components/layout/page-header";
import { formatRelativeTime } from "@/lib/format";
import { analyticsApi, ApiError, type CandidateAccessLogItem } from "@/lib/api";
import { useAuthStore } from "@/stores/auth-store";
import { DashboardGuestGate } from "./dashboard-kit";

/**
 * "Who accessed which candidate" compliance/security view
 * (`GET /analytics/partner/candidate-access-log`,
 * docs/PARTNER_RBAC_ANALYTICS_SPEC.md §"Recruiting Intelligence Read Models").
 * Never shows candidate name/email — only the application/job reference and
 * the acting partner member. Permission-gated: a 403 renders a quiet locked
 * state, not a retry loop.
 */
export function PartnerCandidateAccessLog() {
  const t = useTranslations("dashboard.partnerAccessLog");
  const tc = useTranslations("common");
  const locale = useLocale();
  const status = useAuthStore((s) => s.status);
  const authed = status === "authenticated";

  const query = useQuery({
    queryKey: ["analytics", "partner", "candidate-access-log"],
    queryFn: () => analyticsApi.candidateAccessLog(50),
    enabled: authed,
    retry: false,
  });

  const isForbidden =
    query.isError && query.error instanceof ApiError && query.error.isPermissionError;

  const columns: Column<CandidateAccessLogItem>[] = [
    {
      key: "event_type",
      header: t("table.event"),
      cell: (r) => (t.has(`event.${r.event_type}`) ? t(`event.${r.event_type}`) : r.event_type),
    },
    { key: "job_title", header: t("table.job") },
    { key: "actor_name", header: t("table.actor"), cell: (r) => r.actor_name ?? t("unknownActor") },
    {
      key: "occurred_at",
      header: t("table.time"),
      cell: (r) => formatRelativeTime(r.occurred_at, locale),
    },
    { key: "reason", header: t("table.reason"), cell: (r) => r.reason ?? t("noReason") },
  ];

  return (
    <>
      <PageHeader
        title={t("title")}
        actions={
          <Link href="/partner/ops">
            <Button variant="secondary">{t("backToOps")}</Button>
          </Link>
        }
      />
      <p className="-mt-4 mb-6 max-w-2xl text-sm text-[var(--text-secondary)]">{t("subtitle")}</p>

      {!authed ? (
        <DashboardGuestGate persona="partner" />
      ) : isForbidden ? (
        <EmptyState kind="permission" icon={Lock} title={t("lockedTitle")} description={t("lockedBody")} />
      ) : query.isError ? (
        <EmptyState
          kind="error"
          icon={ShieldCheck}
          title={t("lockedTitle")}
          description={t("lockedBody")}
          action={
            <Button variant="secondary" onClick={() => query.refetch()}>
              {tc("retry")}
            </Button>
          }
        />
      ) : (
        <DataTable
          columns={columns}
          rows={query.data?.items ?? []}
          getRowId={(r) => r.id}
          loading={query.isPending}
          empty={{ kind: "empty", icon: ShieldCheck, title: t("emptyTitle"), description: t("emptyBody") }}
        />
      )}
    </>
  );
}
