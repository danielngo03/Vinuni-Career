"use client";

import { useMemo, useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import { useInfiniteQuery } from "@tanstack/react-query";
import {
  CalendarBlank,
  LightbulbFilament,
  Plus,
  ShieldWarning,
  SignIn,
  Sparkle,
  WarningCircle,
} from "@phosphor-icons/react";
import { Link } from "@/i18n/navigation";
import {
  Button,
  DataTable,
  EmptyState,
  StatusBadge,
  type Column,
} from "@/components/ui";
import { cn } from "@/lib/utils";
import { PageHeader } from "@/components/layout/page-header";
import {
  useEventLabels,
  EVENT_STATUS_TONE,
  EVENT_MODERATION_TONE,
} from "@/lib/events/labels";
import { formatEventWhen } from "@/lib/events/format";
import { ApiError, eventsApi, type OwnerEventSummary } from "@/lib/api";

const STATUS_FILTERS = [
  "all",
  "draft",
  "pending_review",
  "published",
  "rejected",
  "cancelled",
  "completed",
] as const;

type PartnerEventInsightKey =
  | "insightPendingEvents"
  | "insightFillingUp"
  | "insightPublishedActive"
  | "insightNoRegistrations";

function derivePartnerEventInsights(rows: OwnerEventSummary[]): PartnerEventInsightKey[] {
  const out: PartnerEventInsightKey[] = [];
  if (rows.length === 0) return out;
  const pendingCount = rows.filter((r) => r.status === "pending_review").length;
  const publishedCount = rows.filter((r) => r.status === "published").length;
  const fillingUp = rows.some(
    (r) => r.capacity != null && r.capacity > 0 && r.registration_count / r.capacity >= 0.8,
  );
  const noRegistrations = rows.some(
    (r) => r.status === "published" && r.registration_count === 0,
  );
  if (pendingCount > 0) out.push("insightPendingEvents");
  if (fillingUp) out.push("insightFillingUp");
  if (publishedCount > 0 && !fillingUp) out.push("insightPublishedActive");
  if (noRegistrations) out.push("insightNoRegistrations");
  return out.slice(0, 3);
}

export function PartnerEventsScreen() {
  const t = useTranslations("eventsManage");
  const tStates = useTranslations("states");
  const tc = useTranslations("common");
  const locale = useLocale();
  const labels = useEventLabels();

  const [statusFilter, setStatusFilter] = useState<string>("all");

  const query = useInfiniteQuery({
    queryKey: ["events", "mine", statusFilter],
    queryFn: ({ pageParam }) =>
      eventsApi.listMine({
        cursor: pageParam,
        limit: 20,
        status: statusFilter === "all" ? undefined : statusFilter,
      }),
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.page.next_cursor,
    retry: false,
  });

  const rows: OwnerEventSummary[] = useMemo(
    () => query.data?.pages.flatMap((p) => p.data) ?? [],
    [query.data],
  );

  const newButton = (
    <Link href="/partner/events/new">
      <Button variant="primary">
        <Plus aria-hidden weight="bold" className="size-4" />
        {t("newEvent")}
      </Button>
    </Link>
  );

  if (query.isError && query.error instanceof ApiError) {
    const err = query.error;
    if (err.isPermissionError || err.isAuthError) {
      return (
        <>
          <PageHeader title={t("manageTitle")} description={t("manageSubtitle")} />
          <EmptyState
            kind={err.isPermissionError ? "permission" : "auth"}
            icon={err.isPermissionError ? ShieldWarning : SignIn}
            title={
              err.isPermissionError
                ? tStates("permissionTitle")
                : tStates("authTitle")
            }
            description={
              err.isPermissionError ? t("permissionBody") : tStates("authBody")
            }
          />
        </>
      );
    }
  }

  const columns: Column<OwnerEventSummary>[] = [
    {
      key: "title",
      header: t("colTitle"),
      cell: (r) => (
        <Link
          href={`/partner/events/${r.id}`}
          className="font-semibold text-[var(--text-primary)] outline-none hover:text-[var(--brand-primary)] focus-visible:underline"
        >
          {r.title}
        </Link>
      ),
    },
    {
      key: "type",
      header: t("colType"),
      cell: (r) => (
        <span className="text-[var(--text-secondary)]">
          {labels.eventType(r.event_type, r.event_type_label)}
          {" · "}
          {labels.format(r.format, r.format_label)}
        </span>
      ),
    },
    {
      key: "when",
      header: t("colWhen"),
      cell: (r) => (
        <span className="text-[var(--text-secondary)]">
          {formatEventWhen(r.starts_at, r.ends_at, locale)}
        </span>
      ),
    },
    {
      key: "registrations",
      header: t("colRegistrations"),
      cell: (r) => (
        <span className="text-[var(--text-secondary)]">
          {r.capacity != null
            ? `${r.registration_count}/${r.capacity}`
            : r.registration_count}
        </span>
      ),
    },
    {
      key: "status",
      header: t("colStatus"),
      cell: (r) => (
        <div className="flex flex-col items-start gap-1">
          <StatusBadge tone={EVENT_STATUS_TONE[r.status] ?? "info"}>
            {labels.status(r.status, r.status_label)}
          </StatusBadge>
          {r.status === "pending_review" && (
            <StatusBadge tone={EVENT_MODERATION_TONE[r.moderation_status] ?? "info"}>
              {labels.moderation(r.moderation_status, r.moderation_status_label)}
            </StatusBadge>
          )}
        </div>
      ),
    },
    {
      key: "actions",
      header: "",
      align: "right",
      cell: (r) => (
        <Link href={`/partner/events/${r.id}`}>
          <Button variant="ghost" size="sm">
            {t("manage")}
          </Button>
        </Link>
      ),
    },
  ];

  return (
    <>
      <PageHeader
        title={t("manageTitle")}
        description={t("manageSubtitle")}
        actions={newButton}
      />

      {/* ── AI Events Overview ── */}
      {!query.isPending && statusFilter === "all" && (() => {
        const insights = derivePartnerEventInsights(rows);
        if (!insights.length) return null;
        return (
          <section
            aria-label={t("aiInsightsTitle")}
            className="mb-4 rounded-2xl border border-[var(--ai-accent)]/25 bg-gradient-to-br from-[var(--ai-accent-soft)] to-white/60 p-4 "
          >
            <div className="mb-3 flex items-center gap-2">
              <span className="flex size-6 items-center justify-center rounded-lg icon-chip-info shadow-sm">
                <Sparkle aria-hidden weight="duotone" className="size-3.5 text-white" />
              </span>
              <p className="text-sm font-semibold text-[var(--text-primary)]">{t("aiInsightsTitle")}</p>
            </div>
            <ul className="space-y-1.5">
              {insights.map((key) => (
                <li key={key} className="flex items-start gap-2 text-xs text-[var(--text-secondary)]">
                  <LightbulbFilament aria-hidden className="mt-0.5 size-3.5 shrink-0 text-[var(--ai-accent)]" />
                  {t(key)}
                </li>
              ))}
            </ul>
          </section>
        );
      })()}

      {/* Status filter tab chips */}
      {(() => {
        const CHIP_ACTIVE: Record<string, string> = {
          all: "border-[var(--brand-primary)]/30 bg-[var(--brand-primary)] text-white shadow-sm shadow-[var(--brand-primary)]/20",
          draft: "border-[var(--gray-500)]/30 bg-[var(--gray-600)] text-white shadow-sm",
          pending_review: "border-[var(--amber-500)]/30 bg-[var(--amber-600)] text-white shadow-sm",
          published: "border-[var(--teal-500)]/30 bg-[var(--teal-600)] text-white shadow-sm",
          rejected: "border-[var(--red-500)]/30 bg-[var(--red-600)] text-white shadow-sm",
          cancelled: "border-[var(--gray-500)]/30 bg-[var(--gray-600)] text-white shadow-sm",
          completed: "border-teal-500/30 bg-teal-600 text-white shadow-sm",
        };
        return (
          <div className="mb-4 flex flex-wrap gap-2" role="group" aria-label={t("filterStatusLabel")}>
            {STATUS_FILTERS.map((s) => (
              <button
                key={s}
                onClick={() => setStatusFilter(s)}
                aria-pressed={statusFilter === s}
                className={cn(
                  "inline-flex items-center rounded-full border px-3.5 py-1.5 text-xs font-semibold transition-all focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--brand-primary)]",
                  statusFilter === s
                    ? CHIP_ACTIVE[s] ?? CHIP_ACTIVE.all
                    : "border-[var(--border-default)] bg-[var(--surface-card)] text-[var(--text-secondary)] hover:bg-[var(--surface-card)] hover:text-[var(--text-primary)]",
                )}
              >
                {s === "all" ? t("filterAllStatuses") : labels.status(s)}
              </button>
            ))}
          </div>
        );
      })()}

      {query.isError &&
      !(query.error instanceof ApiError && (query.error.isPermissionError || query.error.isAuthError)) ? (
        <EmptyState
          kind="error"
          icon={WarningCircle}
          title={tStates("errorTitle")}
          description={tStates("errorBody")}
          action={
            <Button variant="secondary" onClick={() => query.refetch()}>
              {tc("retry")}
            </Button>
          }
        />
      ) : (
        <>
          <DataTable
            columns={columns}
            rows={rows}
            getRowId={(r) => r.id}
            loading={query.isPending}
            caption={t("manageTitle")}
            empty={{
              kind: "empty",
              icon: CalendarBlank,
              title: statusFilter === "all" ? t("noEventsTitle") : t("noEventsFilterTitle"),
              description: statusFilter === "all" ? t("noEventsBody") : t("noEventsFilterBody"),
              action: statusFilter === "all" ? newButton : undefined,
            }}
          />
          {query.hasNextPage && (
            <div className="mt-6 flex justify-center">
              <Button
                variant="secondary"
                loading={query.isFetchingNextPage}
                onClick={() => query.fetchNextPage()}
              >
                {tc("loadMore")}
              </Button>
            </div>
          )}
        </>
      )}
    </>
  );
}
