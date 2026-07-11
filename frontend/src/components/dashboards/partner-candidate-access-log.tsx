"use client";

import * as React from "react";
import { useLocale, useTranslations } from "next-intl";
import { useQuery } from "@tanstack/react-query";
import { ShieldAlert, Eye, Download, FileText, UserCheck, ArrowLeft } from "lucide-react";
import { Link } from "@/i18n/navigation";
import { Button } from "@/components/ui";
import { PageHeader } from "@/components/layout/page-header";
import {
  AttentionPanel,
  type AttentionItem,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardToolbar,
  DataTable,
  type ColumnDef,
  EmptyState,
  StatusChip,
  type ChipTone,
} from "@/components/kit";
import { formatRelativeTime } from "@/lib/format";
import {
  analyticsApi,
  organizationApi,
  ApiError,
  type CandidateAccessEventType,
  type CandidateAccessLogItem,
} from "@/lib/api";
import { useAuthStore } from "@/stores/auth-store";
import { DashboardGuestGate } from "./dashboard-kit";

/** Event → chip tone + icon. More sensitive events get a hotter tone. */
const EVENT_META: Record<CandidateAccessEventType, { tone: ChipTone; icon: React.ElementType }> = {
  application_opened: { tone: "neutral", icon: FileText },
  cv_previewed: { tone: "info", icon: Eye },
  cv_downloaded: { tone: "warning", icon: Download },
  identity_reveal_requested: { tone: "violet", icon: UserCheck },
  identity_revealed_viewed: { tone: "danger", icon: ShieldAlert },
};

/** The events that count toward an access-spike (identity/CV egress). */
const SENSITIVE: ReadonlySet<CandidateAccessEventType> = new Set([
  "cv_downloaded",
  "identity_reveal_requested",
  "identity_revealed_viewed",
]);

const SPIKE_THRESHOLD = 4;

/**
 * Candidate access log — the partner security/compliance surface. Shows WHO
 * (partner member) accessed WHICH application/job and why, never candidate PII.
 * A permission-locked (403) response renders a quiet locked state (no retry
 * loop). Access-spike alerts are derived from the real event stream (a member
 * with many CV downloads / identity reveals in the window) — no fabricated data.
 */
export function PartnerCandidateAccessLog() {
  const t = useTranslations("dashboard.partnerAccessLog");
  const tc = useTranslations("common");
  const locale = useLocale();
  const authed = useAuthStore((s) => s.status === "authenticated");

  // members/me capability map — gate the surface before firing the log query.
  const capsQ = useQuery({
    queryKey: ["org", "me", "capabilities"],
    queryFn: () => organizationApi.getMyCapabilities(),
    enabled: authed,
    retry: false,
  });
  const caps = capsQ.data;
  const canView = caps
    ? caps.is_org_admin ||
      Boolean(caps.capabilities["analytics:view_clicks"]) ||
      Boolean(caps.capabilities["candidate_identity:download_cv"])
    : true;

  const query = useQuery({
    queryKey: ["analytics", "partner", "candidate-access-log"],
    queryFn: () => analyticsApi.candidateAccessLog(50),
    enabled: authed && canView && !capsQ.isError,
    retry: false,
  });

  const items = query.data?.items ?? [];

  // Derive access-spike alerts from the real events: members with an unusual
  // volume of sensitive (CV-egress / reveal) accesses in the returned window.
  const spikes = React.useMemo<AttentionItem[]>(() => {
    const byActor = new Map<string, number>();
    for (const e of items) {
      if (!SENSITIVE.has(e.event_type)) continue;
      const key = e.actor_name ?? t("unknownActor");
      byActor.set(key, (byActor.get(key) ?? 0) + 1);
    }
    return [...byActor.entries()]
      .filter(([, count]) => count >= SPIKE_THRESHOLD)
      .sort((a, b) => b[1] - a[1])
      .map(([actor, count]) => ({
        key: actor,
        label: t("spikeItem", { actor, count }),
        href: "/partner/team",
        icon: ShieldAlert,
        tone: "danger" as ChipTone,
        meta: t("reviewAccess"),
      }));
  }, [items, t]);

  const capsForbidden =
    capsQ.isError && capsQ.error instanceof ApiError && capsQ.error.isPermissionError;
  const logForbidden =
    query.isError && query.error instanceof ApiError && query.error.isPermissionError;
  const locked = (caps && !canView) || capsForbidden || logForbidden;

  const columns: ColumnDef<CandidateAccessLogItem, unknown>[] = [
    {
      accessorKey: "event_type",
      header: t("table.event"),
      cell: ({ row }) => {
        const meta = EVENT_META[row.original.event_type];
        const Icon = meta?.icon ?? FileText;
        const label = t.has(`event.${row.original.event_type}`)
          ? t(`event.${row.original.event_type}`)
          : row.original.event_type;
        return (
          <StatusChip tone={meta?.tone ?? "neutral"}>
            <Icon aria-hidden className="size-3.5" strokeWidth={1.9} />
            {label}
          </StatusChip>
        );
      },
    },
    {
      accessorKey: "job_title",
      header: t("table.job"),
      cell: ({ row }) => <span className="font-medium text-foreground">{row.original.job_title}</span>,
    },
    {
      accessorKey: "actor_name",
      header: t("table.actor"),
      cell: ({ row }) => row.original.actor_name ?? t("unknownActor"),
    },
    {
      accessorKey: "reason",
      header: t("table.reason"),
      cell: ({ row }) => (
        <span className="text-muted-foreground">{row.original.reason ?? t("noReason")}</span>
      ),
    },
    {
      accessorKey: "occurred_at",
      header: t("table.time"),
      meta: { align: "right" },
      cell: ({ row }) => (
        <span className="whitespace-nowrap tabular-nums text-muted-foreground">
          {formatRelativeTime(row.original.occurred_at, locale)}
        </span>
      ),
    },
  ];

  return (
    <>
      <PageHeader
        title={t("title")}
        subtitle={t("subtitle")}
        actions={
          <Link href="/partner/ops">
            <Button variant="secondary" size="sm">
              <ArrowLeft className="size-4" strokeWidth={1.8} />
              {t("backToOps")}
            </Button>
          </Link>
        }
      />

      {!authed ? (
        <DashboardGuestGate persona="partner" />
      ) : locked ? (
        <EmptyState kind="permission" title={t("lockedTitle")} description={t("lockedBody")} />
      ) : query.isError ? (
        <EmptyState
          kind="error"
          title={t("errorTitle")}
          description={t("errorBody")}
          action={
            <Button variant="secondary" onClick={() => query.refetch()}>
              {tc("retry")}
            </Button>
          }
        />
      ) : (
        <div className="space-y-4">
          {spikes.length > 0 && (
            <Card className="border-l-[3px]" style={{ borderLeftColor: "var(--content-danger)" }}>
              <CardHeader>
                <CardTitle>{t("spikeTitle")}</CardTitle>
                <CardToolbar>
                  <ShieldAlert
                    className="size-4"
                    strokeWidth={1.9}
                    style={{ color: "var(--content-danger)" }}
                  />
                </CardToolbar>
              </CardHeader>
              <CardContent>
                <p className="mb-2.5 type-caption text-muted-foreground">{t("spikeNote")}</p>
                <AttentionPanel items={spikes} />
              </CardContent>
            </Card>
          )}

          <DataTable
            columns={columns}
            data={items}
            getRowId={(r) => r.id}
            loading={query.isPending}
            pageSize={15}
            empty={<EmptyState kind="empty" title={t("emptyTitle")} description={t("emptyBody")} />}
          />
        </div>
      )}
    </>
  );
}
