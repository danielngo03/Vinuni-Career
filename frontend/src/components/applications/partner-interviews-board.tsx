"use client";

import * as React from "react";
import { useLocale, useTranslations } from "next-intl";
import { useQuery } from "@tanstack/react-query";
import {
  AlertCircle,
  CalendarClock,
  CalendarDays,
  CheckCircle2,
  ExternalLink,
  Filter,
  LogIn,
  ShieldAlert,
  UserX,
  Video,
} from "lucide-react";
import { Button } from "@/components/ui";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import {
  DataTable,
  type ColumnDef,
  DetailSheet,
  EmptyState,
  FilterBar,
  KpiRow,
  KpiTile,
  PageHeader,
  StatusChip,
  type ChipTone,
} from "@/components/kit";
import { formatDateTime } from "@/lib/format";
import {
  ApiError,
  organizationApi,
  recruitingApi,
  type InterviewBoardRow,
  type InterviewBoardScope,
} from "@/lib/api";
import { INTERVIEW_STATUS_CHIP, initials } from "./chip-tones";
import { AssigneeStack, SegmentedFilter } from "./recruiting-board-parts";
import { PartnerInterviewPanel } from "./partner-interview-panel";

const nf = new Intl.NumberFormat();

/** Categorical hues for the delivery channel (a genuine category, not a state). */
const MODE_CHIP: Record<string, ChipTone> = {
  onsite: "indigo",
  online: "sky",
  phone: "teal",
};

const SCOPES: readonly InterviewBoardScope[] = ["upcoming", "past", "all"];
const STATUS_OPTIONS = ["all", "scheduled", "completed", "cancelled", "no_show"] as const;
type StatusFilter = (typeof STATUS_OPTIONS)[number];

const WEEK_MS = 7 * 24 * 60 * 60 * 1000;

/** A future scheduled interview (the "upcoming" bucket). */
function isUpcoming(row: InterviewBoardRow, now: number): boolean {
  return row.status === "scheduled" && new Date(row.scheduled_at).getTime() >= now;
}

/**
 * Org-wide Interviews board (v10). One bounded `scope=all` snapshot feeds honest
 * KPIs + a segmented time-window / status / "mine" client filter; each row is a
 * leak-safe glance and clicking one opens the full, actionable interview panel
 * (schedule/reschedule/cancel/complete) for that application.
 */
export function PartnerInterviewsBoard() {
  const t = useTranslations("interviews");
  const tStates = useTranslations("states");
  const tc = useTranslations("common");
  const locale = useLocale();

  const [scope, setScope] = React.useState<InterviewBoardScope>("upcoming");
  const [statusFilter, setStatusFilter] = React.useState<StatusFilter>("all");
  const [mineOnly, setMineOnly] = React.useState(false);
  const [search, setSearch] = React.useState("");
  const [selected, setSelected] = React.useState<InterviewBoardRow | null>(null);

  // One bounded snapshot (scope=all) → honest KPI counts + client-side filters.
  const query = useQuery({
    queryKey: ["recruiting", "interviews", "board"],
    queryFn: () => recruitingApi.listInterviewsBoard({ scope: "all", limit: 200 }),
    staleTime: 30_000,
    refetchInterval: 60_000,
    retry: false,
  });

  // Caller capabilities gate the panel's write actions (advisory; the service
  // layer stays authoritative). `interviews:schedule` = manage interviews.
  const capsQuery = useQuery({
    queryKey: ["org", "me", "capabilities"],
    queryFn: () => organizationApi.getMyCapabilities(),
    staleTime: 60_000,
    retry: false,
  });
  const caps = capsQuery.data;
  const canSchedule = caps
    ? caps.is_org_admin || caps.grants.includes("interviews:schedule")
    : false;

  const rows = React.useMemo(() => query.data?.interviews ?? [], [query.data]);
  const total = query.data?.total ?? rows.length;

  const metrics = React.useMemo(() => {
    const now = Date.now();
    let upcoming = 0;
    let thisWeek = 0;
    let completed = 0;
    let noShow = 0;
    for (const r of rows) {
      if (isUpcoming(r, now)) {
        upcoming += 1;
        if (new Date(r.scheduled_at).getTime() - now <= WEEK_MS) thisWeek += 1;
      }
      if (r.status === "completed") completed += 1;
      if (r.status === "no_show") noShow += 1;
    }
    return { upcoming, thisWeek, completed, noShow };
  }, [rows]);

  const visibleRows = React.useMemo(() => {
    const now = Date.now();
    let out = rows;
    if (scope === "upcoming") out = out.filter((r) => isUpcoming(r, now));
    else if (scope === "past") out = out.filter((r) => !isUpcoming(r, now));
    if (statusFilter !== "all") out = out.filter((r) => r.status === statusFilter);
    if (mineOnly) out = out.filter((r) => r.is_attendee);
    const q = search.trim().toLowerCase();
    if (q) {
      out = out.filter(
        (r) =>
          r.candidate_handle.toLowerCase().includes(q) ||
          r.job_title.toLowerCase().includes(q),
      );
    }
    // Upcoming = soonest first; everything else = most recent first.
    const asc = scope === "upcoming";
    return [...out].sort((a, b) => {
      const da = new Date(a.scheduled_at).getTime();
      const db = new Date(b.scheduled_at).getTime();
      return asc ? da - db : db - da;
    });
  }, [rows, scope, statusFilter, mineOnly, search]);

  const header = <PageHeader title={t("board.title")} subtitle={t("board.subtitle")} />;

  /* ---- permission / auth / error gates ---- */
  if (query.isError && query.error instanceof ApiError) {
    const err = query.error;
    if (err.isPermissionError || err.isAuthError) {
      return (
        <>
          {header}
          <EmptyState
            kind={err.isPermissionError ? "permission" : "auth"}
            icon={err.isPermissionError ? ShieldAlert : LogIn}
            title={err.isPermissionError ? tStates("permissionTitle") : tStates("authTitle")}
            description={err.isPermissionError ? tStates("permissionBody") : tStates("authBody")}
          />
        </>
      );
    }
    return (
      <>
        {header}
        <EmptyState
          kind={err.code === "NETWORK_ERROR" ? "offline" : "error"}
          icon={AlertCircle}
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

  const statusText = (row: InterviewBoardRow) =>
    STATUS_OPTIONS.includes(row.status as StatusFilter)
      ? t(`status.${row.status}`)
      : row.status_label;

  const columns: ColumnDef<InterviewBoardRow, unknown>[] = [
    {
      id: "candidate",
      enableSorting: false,
      header: t("board.colCandidate"),
      cell: ({ row }) => {
        const r = row.original;
        return (
          <span className="inline-flex min-w-0 items-center gap-2.5">
            <Avatar size="sm">
              <AvatarFallback>{initials(r.candidate_handle)}</AvatarFallback>
            </Avatar>
            <span className="min-w-0 truncate font-medium text-foreground">
              {r.candidate_handle}
            </span>
          </span>
        );
      },
    },
    {
      id: "job",
      enableSorting: false,
      header: t("board.colJob"),
      cell: ({ row }) => {
        const r = row.original;
        return (
          <span className="min-w-0">
            <span className="block truncate text-foreground">{r.job_title}</span>
            {r.stage_name && (
              <span className="type-caption text-muted-foreground">{r.stage_name}</span>
            )}
          </span>
        );
      },
    },
    {
      id: "mode",
      enableSorting: false,
      header: t("board.colMode"),
      cell: ({ row }) => (
        <StatusChip tone={MODE_CHIP[row.original.mode] ?? "neutral"} size="sm">
          {row.original.mode_label || t(`mode.${row.original.mode}`)}
        </StatusChip>
      ),
    },
    {
      id: "schedule",
      enableSorting: false,
      header: t("board.colSchedule"),
      cell: ({ row }) => {
        const r = row.original;
        return (
          <span className="min-w-0">
            <span className="block truncate type-small tabular-nums text-foreground">
              {formatDateTime(r.scheduled_at, locale)}
            </span>
            <span className="type-caption tabular-nums text-muted-foreground">
              {t("durationValue", { minutes: r.duration_minutes })}
            </span>
          </span>
        );
      },
    },
    {
      id: "interviewers",
      enableSorting: false,
      header: t("board.colInterviewers"),
      cell: ({ row }) => {
        const r = row.original;
        const shown = r.assignees.slice(0, 3).map((a) => a.display_name);
        return (
          <AssigneeStack
            names={shown}
            extra={Math.max(0, r.assignee_count - shown.length)}
            emptyLabel={t("board.noInterviewers")}
          />
        );
      },
    },
    {
      id: "status",
      enableSorting: false,
      header: t("board.colStatus"),
      meta: { align: "right" },
      cell: ({ row }) => (
        <span className="flex justify-end">
          <StatusChip tone={INTERVIEW_STATUS_CHIP[row.original.status] ?? "neutral"}>
            {statusText(row.original)}
          </StatusChip>
        </span>
      ),
    },
  ];

  const noData = rows.length === 0;

  return (
    <>
      {header}
      <div className="space-y-4">
        <KpiRow cols={4}>
          <KpiTile
            label={t("board.kpiUpcoming")}
            value={query.isPending ? "—" : nf.format(metrics.upcoming)}
            icon={CalendarClock}
          />
          <KpiTile
            label={t("board.kpiThisWeek")}
            value={query.isPending ? "—" : nf.format(metrics.thisWeek)}
            icon={CalendarDays}
            hint={metrics.thisWeek > 0 ? t("board.kpiThisWeekHint") : undefined}
          />
          <KpiTile
            label={t("board.kpiCompleted")}
            value={query.isPending ? "—" : nf.format(metrics.completed)}
            icon={CheckCircle2}
          />
          <KpiTile
            label={t("board.kpiNoShow")}
            value={query.isPending ? "—" : nf.format(metrics.noShow)}
            icon={UserX}
          />
        </KpiRow>

        <FilterBar
          search={{
            value: search,
            onChange: setSearch,
            placeholder: t("board.searchPlaceholder"),
            ariaLabel: t("board.searchPlaceholder"),
          }}
          actions={
            !query.isPending && rows.length > 0 ? (
              <span className="type-caption tabular-nums text-muted-foreground">
                {rows.length < total
                  ? t("board.boundedHint", { shown: rows.length, total })
                  : t("board.resultCount", { count: visibleRows.length })}
              </span>
            ) : undefined
          }
        >
          <SegmentedFilter
            value={scope}
            options={SCOPES}
            onChange={setScope}
            label={t("board.scopeLabel")}
            optionLabel={(s) => t(`board.scope_${s}`)}
          />
          <SegmentedFilter
            value={statusFilter}
            options={STATUS_OPTIONS}
            onChange={setStatusFilter}
            label={t("board.filterStatusLabel")}
            optionLabel={(s) => (s === "all" ? t("board.statusAll") : t(`status.${s}`))}
          />
          <button
            type="button"
            onClick={() => setMineOnly((v) => !v)}
            aria-pressed={mineOnly}
            className={
              mineOnly
                ? "inline-flex h-9 items-center gap-1.5 rounded-lg border border-transparent bg-foreground px-3 text-[0.8125rem] font-semibold text-background"
                : "inline-flex h-9 items-center gap-1.5 rounded-lg border border-border bg-card px-3 text-[0.8125rem] font-medium text-muted-foreground transition-colors hover:text-foreground"
            }
          >
            <Filter aria-hidden className="size-4" strokeWidth={1.8} />
            {t("board.mineToggle")}
          </button>
        </FilterBar>

        <DataTable
          columns={columns}
          data={visibleRows}
          getRowId={(r) => r.id}
          loading={query.isPending}
          pageSize={12}
          activeRowId={selected?.id}
          onRowClick={(r) => setSelected(r)}
          empty={
            <EmptyState
              kind="empty"
              icon={CalendarClock}
              title={noData ? t("board.emptyTitle") : t("board.noMatchTitle")}
              description={noData ? t("board.emptyBody") : t("board.noMatchBody")}
              action={
                !noData ? (
                  <Button
                    variant="secondary"
                    onClick={() => {
                      setScope("all");
                      setStatusFilter("all");
                      setMineOnly(false);
                      setSearch("");
                    }}
                  >
                    {t("board.clearFilters")}
                  </Button>
                ) : undefined
              }
            />
          }
        />
      </div>

      {/* Interview detail drawer — full actionable panel for the application.
          Refetch the board on close so a reschedule/cancel/complete taken inside
          the panel is reflected in the list + KPIs immediately. */}
      <DetailSheet
        open={!!selected}
        onClose={() => {
          setSelected(null);
          void query.refetch();
        }}
        width="lg"
        closeLabel={tc("close")}
        title={selected?.candidate_handle ?? ""}
        subtitle={selected?.job_title}
        avatar={
          selected ? (
            <Avatar size="lg">
              <AvatarFallback>{initials(selected.candidate_handle)}</AvatarFallback>
            </Avatar>
          ) : undefined
        }
        status={
          selected ? (
            <>
              <StatusChip tone={INTERVIEW_STATUS_CHIP[selected.status] ?? "neutral"}>
                {statusText(selected)}
              </StatusChip>
              <StatusChip tone={MODE_CHIP[selected.mode] ?? "neutral"} size="sm">
                {selected.mode_label || t(`mode.${selected.mode}`)}
              </StatusChip>
              {selected.stage_name && (
                <StatusChip tone="indigo" size="sm">
                  {selected.stage_name}
                </StatusChip>
              )}
            </>
          ) : undefined
        }
        headerActions={
          selected?.meeting_link ? (
            <a
              href={selected.meeting_link}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex h-9 items-center gap-1.5 rounded-lg border border-border bg-card px-3 text-[0.8125rem] font-medium text-foreground outline-none transition-colors hover:bg-[var(--bg-subtle)] focus-visible:ring-2 focus-visible:ring-[var(--field-focus-border)]"
            >
              <Video aria-hidden className="size-4" strokeWidth={1.8} />
              {t("board.joinCta")}
              <ExternalLink aria-hidden className="size-3.5 text-muted-foreground" strokeWidth={1.8} />
            </a>
          ) : undefined
        }
      >
        {selected && (
          <div className="p-5">
            <PartnerInterviewPanel
              key={selected.application_id}
              applicationId={selected.application_id}
              canSchedule={canSchedule}
            />
          </div>
        )}
      </DetailSheet>
    </>
  );
}
