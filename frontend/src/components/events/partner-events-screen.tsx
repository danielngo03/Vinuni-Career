"use client";

import * as React from "react";
import { useLocale, useTranslations } from "next-intl";
import { useInfiniteQuery } from "@tanstack/react-query";
import { CalendarClock, ClipboardCheck, ExternalLink, Plus, Ticket, Users } from "lucide-react";
import { Link } from "@/i18n/navigation";
import { Button } from "@/components/ui";
import {
  DataTable,
  type ColumnDef,
  DetailRow,
  DetailSheet,
  DetailSheetSection,
  EmptyState,
  FilterBar,
  KpiRow,
  KpiTile,
  PageHeader,
  StatusChip,
  type ChipTone,
} from "@/components/kit";
import { cn } from "@/lib/utils";
import { useEventLabels } from "@/lib/events/labels";
import { formatEventWhen } from "@/lib/events/format";
import { ApiError, eventsApi, type EventStatus, type OwnerEventSummary } from "@/lib/api";

const nf = new Intl.NumberFormat();

const STATUS_FILTERS = [
  "all",
  "draft",
  "pending_review",
  "published",
  "rejected",
  "cancelled",
  "completed",
] as const;

const EVENT_STATUS_CHIP: Record<EventStatus, ChipTone> = {
  draft: "neutral",
  pending_review: "warning",
  published: "success",
  cancelled: "neutral",
  completed: "sky",
  rejected: "danger",
};

function fillPct(r: OwnerEventSummary): number | null {
  if (r.capacity == null || r.capacity <= 0) return null;
  return Math.min(100, Math.round((r.registration_count / r.capacity) * 100));
}

export function PartnerEventsScreen() {
  const t = useTranslations("eventsManage");
  const tStates = useTranslations("states");
  const tc = useTranslations("common");
  const locale = useLocale();
  const labels = useEventLabels();

  const [statusFilter, setStatusFilter] = React.useState<string>("all");
  const [search, setSearch] = React.useState("");
  const [detailId, setDetailId] = React.useState<string | null>(null);

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

  const rows: OwnerEventSummary[] = React.useMemo(
    () => query.data?.pages.flatMap((p) => p.data) ?? [],
    [query.data],
  );

  const detailEvent = detailId ? (rows.find((r) => r.id === detailId) ?? null) : null;

  const kpi = React.useMemo(() => {
    let published = 0;
    let pending = 0;
    let regs = 0;
    for (const r of rows) {
      if (r.status === "published") published += 1;
      if (r.status === "pending_review") pending += 1;
      regs += r.registration_count;
    }
    return { total: rows.length, published, pending, regs };
  }, [rows]);

  const newButton = (
    <Link href="/partner/events/new">
      <Button variant="primary" size="sm">
        <Plus className="size-4" strokeWidth={2} />
        {t("newEvent")}
      </Button>
    </Link>
  );

  const header = <PageHeader title={t("manageTitle")} subtitle={t("manageSubtitle")} actions={newButton} />;

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

  const columns: ColumnDef<OwnerEventSummary, unknown>[] = [
    {
      accessorKey: "title",
      header: t("colTitle"),
      cell: ({ row }) => <span className="font-semibold text-foreground">{row.original.title}</span>,
    },
    {
      id: "type",
      header: t("colType"),
      cell: ({ row }) => (
        <span className="type-small text-muted-foreground">
          {labels.eventType(row.original.event_type, row.original.event_type_label)}
          {" · "}
          {labels.format(row.original.format, row.original.format_label)}
        </span>
      ),
    },
    {
      id: "when",
      header: t("colWhen"),
      cell: ({ row }) => (
        <span className="type-small text-muted-foreground">
          {formatEventWhen(row.original.starts_at, row.original.ends_at, locale)}
        </span>
      ),
    },
    {
      accessorKey: "registration_count",
      header: t("colRegistrations"),
      meta: { align: "right" },
      cell: ({ row }) => <RegistrationCell row={row.original} />,
    },
    {
      accessorKey: "status",
      header: t("colStatus"),
      cell: ({ row }) => (
        <StatusChip tone={EVENT_STATUS_CHIP[row.original.status] ?? "neutral"} dot>
          {labels.status(row.original.status, row.original.status_label)}
        </StatusChip>
      ),
    },
  ];

  return (
    <>
      {header}

      {rows.length > 0 && (
        <KpiRow cols={4} className="mb-4">
          <KpiTile label={t("kpi.total")} value={nf.format(kpi.total)} icon={CalendarClock} />
          <KpiTile label={t("kpi.published")} value={nf.format(kpi.published)} icon={ClipboardCheck} />
          <KpiTile label={t("kpi.pending")} value={nf.format(kpi.pending)} icon={CalendarClock} />
          <KpiTile label={t("kpi.registrations")} value={nf.format(kpi.regs)} icon={Users} />
        </KpiRow>
      )}

      <FilterBar
        className="mb-4"
        search={{ value: search, onChange: setSearch, placeholder: t("searchPlaceholder") }}
      >
        <div className="flex flex-wrap gap-1.5" role="group" aria-label={t("filterStatusLabel")}>
          {STATUS_FILTERS.map((s) => (
            <button
              key={s}
              onClick={() => setStatusFilter(s)}
              aria-pressed={statusFilter === s}
              className={cn(
                "inline-flex items-center rounded-full border px-3 py-1 text-[0.8125rem] font-medium transition-colors outline-none focus-visible:ring-2 focus-visible:ring-[var(--field-focus-border)]",
                statusFilter === s
                  ? "border-transparent bg-foreground text-[var(--surface-card)]"
                  : "border-border bg-card text-muted-foreground hover:text-foreground",
              )}
            >
              {s === "all" ? t("filterAllStatuses") : labels.status(s)}
            </button>
          ))}
        </div>
      </FilterBar>

      {query.isError && !(query.error instanceof ApiError && (query.error.isPermissionError || query.error.isAuthError)) ? (
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
      ) : (
        <>
          <DataTable
            columns={columns}
            data={rows}
            getRowId={(r) => r.id}
            globalFilter={search}
            loading={query.isPending}
            onRowClick={(r) => setDetailId(r.id)}
            activeRowId={detailId ?? undefined}
            empty={
              <EmptyState
                kind="empty"
                title={statusFilter === "all" ? t("noEventsTitle") : t("noEventsFilterTitle")}
                description={statusFilter === "all" ? t("noEventsBody") : t("noEventsFilterBody")}
                action={statusFilter === "all" ? newButton : undefined}
              />
            }
          />
          {query.hasNextPage && (
            <div className="mt-4 flex justify-center">
              <Button variant="secondary" loading={query.isFetchingNextPage} onClick={() => query.fetchNextPage()}>
                {t("loadMore")}
              </Button>
            </div>
          )}
        </>
      )}

      <EventQuickSheet event={detailEvent} onClose={() => setDetailId(null)} />
    </>
  );
}

function RegistrationCell({ row }: { row: OwnerEventSummary }) {
  const pct = fillPct(row);
  return (
    <div className="inline-flex flex-col items-end gap-1">
      <span className="font-semibold tabular-nums text-foreground">
        {row.capacity != null ? `${nf.format(row.registration_count)} / ${nf.format(row.capacity)}` : nf.format(row.registration_count)}
      </span>
      {pct != null && (
        <span className="h-1.5 w-16 overflow-hidden rounded-full bg-[var(--bg-muted)]">
          <span
            className="block h-full rounded-full"
            style={{ width: `${Math.max(pct, row.registration_count > 0 ? 4 : 0)}%`, background: "var(--viz-indigo)" }}
          />
        </span>
      )}
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* Quick-view sheet                                                             */
/* -------------------------------------------------------------------------- */

function EventQuickSheet({ event, onClose }: { event: OwnerEventSummary | null; onClose: () => void }) {
  const t = useTranslations("eventsManage");
  const tc = useTranslations("common");
  const locale = useLocale();
  const labels = useEventLabels();

  if (!event) return null;
  const e = event;
  const pct = fillPct(e);
  const where =
    e.format === "online"
      ? t("sheet.online")
      : e.venue
        ? [e.venue.name, e.venue.address].filter(Boolean).join(" · ") || "—"
        : "—";

  return (
    <DetailSheet
      open={!!event}
      onClose={onClose}
      title={e.title}
      subtitle={`${labels.eventType(e.event_type, e.event_type_label)} · ${labels.format(e.format, e.format_label)}`}
      closeLabel={tc("close")}
      status={
        <StatusChip tone={EVENT_STATUS_CHIP[e.status] ?? "neutral"} dot>
          {labels.status(e.status, e.status_label)}
        </StatusChip>
      }
      footer={
        <>
          {e.status === "published" && (
            <Link href={`/events/${e.slug}`} target="_blank">
              <Button variant="ghost" size="sm">
                <ExternalLink className="size-4" strokeWidth={1.8} />
                {t("sheet.preview")}
              </Button>
            </Link>
          )}
          <Link href={`/partner/events/${e.id}`}>
            <Button variant="primary" size="sm">
              {t("sheet.openManage")}
            </Button>
          </Link>
        </>
      }
    >
      <DetailSheetSection title={t("sheet.registrations")}>
        <div className="flex items-end justify-between gap-3">
          <div>
            <div className="flex items-baseline gap-1.5">
              <span className="type-metric text-foreground">{nf.format(e.registration_count)}</span>
              {e.capacity != null && (
                <span className="type-small text-muted-foreground">/ {nf.format(e.capacity)}</span>
              )}
            </div>
            <p className="type-caption mt-0.5 text-muted-foreground">
              {e.capacity != null ? `${pct}% ${t("sheet.fillRate").toLowerCase()}` : t("sheet.unlimited")}
            </p>
          </div>
          <Ticket className="size-8 text-muted-foreground" strokeWidth={1.4} />
        </div>
        {pct != null && (
          <span className="mt-3 block h-2 overflow-hidden rounded-full bg-[var(--bg-muted)]">
            <span
              className="block h-full rounded-full"
              style={{ width: `${Math.max(pct, e.registration_count > 0 ? 4 : 0)}%`, background: "var(--viz-indigo)" }}
            />
          </span>
        )}
      </DetailSheetSection>

      <DetailSheetSection title={t("sheet.title")}>
        <dl>
          <DetailRow label={t("sheet.when")}>{formatEventWhen(e.starts_at, e.ends_at, locale)}</DetailRow>
          <DetailRow label={t("sheet.where")}>{where}</DetailRow>
          <DetailRow label={t("sheet.capacity")}>
            {e.capacity != null ? nf.format(e.capacity) : t("sheet.unlimited")}
          </DetailRow>
          <DetailRow label={t("sheet.publishState")}>
            <StatusChip tone={EVENT_STATUS_CHIP[e.status] ?? "neutral"} size="sm">
              {labels.status(e.status, e.status_label)}
            </StatusChip>
          </DetailRow>
        </dl>
      </DetailSheetSection>
    </DetailSheet>
  );
}
