"use client";

import * as React from "react";
import { useTranslations } from "next-intl";
import { useInfiniteQuery } from "@tanstack/react-query";
import {
  Briefcase,
  CheckCircle2,
  Clock,
  FileText,
  ShieldAlert,
  LogIn,
  Users,
  Users2,
} from "lucide-react";
import { Link, useRouter } from "@/i18n/navigation";
import { Button } from "@/components/ui";
import {
  DataTable,
  type ColumnDef,
  EmptyState,
  FilterBar,
  KpiRow,
  KpiTile,
  PageHeader,
  StatusChip,
  type ChipTone,
} from "@/components/kit";
import { useJobLabels } from "@/lib/jobs/labels";
import { formatLocation } from "@/lib/jobs/format";
import { ApiError, jobsApi, type OwnerJobSummary } from "@/lib/api";

const JOB_STATUS_CHIP: Record<string, ChipTone> = {
  draft: "neutral",
  pending_review: "warning",
  active: "success",
  rejected: "danger",
  closed: "neutral",
  expired: "neutral",
};

const nf = new Intl.NumberFormat();

/**
 * Partner Candidates index (v10). A job picker: the recruiter chooses a posting
 * to open its applicant workspace. Real `GET /jobs/mine` data feeds honest
 * job-posting KPIs, a searchable/status-filterable DataTable, and per-row deep
 * links into `/partner/jobs/{id}/applications`. No fabricated applicant counts
 * (the list projection does not carry them).
 */
export function PartnerCandidatesIndex() {
  const t = useTranslations("candidates");
  const tJobs = useTranslations("jobs");
  const tStates = useTranslations("states");
  const tc = useTranslations("common");
  const labels = useJobLabels();
  const router = useRouter();

  const [search, setSearch] = React.useState("");
  const [statusFilter, setStatusFilter] = React.useState<string>("all");

  const query = useInfiniteQuery({
    queryKey: ["jobs", "mine", "candidates"],
    queryFn: ({ pageParam }) => jobsApi.listMine({ cursor: pageParam, limit: 20 }),
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.page.next_cursor,
    retry: false,
  });

  // Auto-load the full set (bounded) so KPI counts + filtering are honest.
  const pageCount = query.data?.pages.length ?? 0;
  React.useEffect(() => {
    if (query.hasNextPage && !query.isFetchingNextPage && pageCount < 40) {
      void query.fetchNextPage();
    }
  }, [query.hasNextPage, query.isFetchingNextPage, pageCount, query]);

  const rows: OwnerJobSummary[] = React.useMemo(
    () => query.data?.pages.flatMap((p) => p.data) ?? [],
    [query.data],
  );

  const allLoaded = !query.hasNextPage || pageCount >= 40;

  const metrics = React.useMemo(() => {
    const active = rows.filter((r) => r.status === "active").length;
    const pending = rows.filter(
      (r) => r.status === "pending_review" || r.moderation_status === "pending",
    ).length;
    const drafts = rows.filter((r) => r.status === "draft").length;
    return { total: rows.length, active, pending, drafts };
  }, [rows]);

  const filteredRows = React.useMemo(
    () =>
      statusFilter === "all" ? rows : rows.filter((r) => r.status === statusFilter),
    [rows, statusFilter],
  );

  const header = (
    <PageHeader
      title={t("indexTitle")}
      subtitle={t("indexSubtitle")}
      actions={
        <Link href="/partner/jobs">
          <Button variant="secondary" size="sm">
            <Briefcase className="size-4" strokeWidth={1.8} />
            {t("goToJobs")}
          </Button>
        </Link>
      }
    />
  );

  /* ---- Permission / auth gates ---- */
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

  const columns: ColumnDef<OwnerJobSummary, unknown>[] = [
    {
      id: "title",
      accessorFn: (r) => r.title,
      header: tJobs("colTitle"),
      cell: ({ row }) => (
        <Link
          href={`/partner/jobs/${row.original.id}/applications`}
          onClick={(e) => e.stopPropagation()}
          className="font-semibold text-foreground outline-none hover:text-[var(--brand-primary)] focus-visible:underline"
        >
          {row.original.title}
        </Link>
      ),
    },
    {
      id: "type",
      enableSorting: false,
      header: tJobs("colType"),
      cell: ({ row }) => (
        <span className="type-small text-muted-foreground">
          {labels.employmentType(row.original.employment_type, row.original.employment_type_label)}
          {" · "}
          {labels.locationType(row.original.location_type, row.original.location_type_label)}
        </span>
      ),
    },
    {
      id: "location",
      enableSorting: false,
      header: tJobs("location"),
      cell: ({ row }) => (
        <span className="type-small text-muted-foreground">
          {formatLocation(row.original.location_city, row.original.location_country)}
        </span>
      ),
    },
    {
      id: "status",
      accessorFn: (r) => r.status,
      header: tJobs("colStatus"),
      cell: ({ row }) => (
        <StatusChip tone={JOB_STATUS_CHIP[row.original.status] ?? "neutral"}>
          {labels.status(row.original.status, row.original.status_label)}
        </StatusChip>
      ),
    },
    {
      id: "actions",
      enableSorting: false,
      meta: { align: "right" },
      header: "",
      cell: ({ row }) => (
        <Link
          href={`/partner/jobs/${row.original.id}/applications`}
          onClick={(e) => e.stopPropagation()}
        >
          <Button variant="ghost" size="sm">
            <Users2 aria-hidden className="size-4" strokeWidth={1.8} />
            {tJobs("viewCandidates")}
          </Button>
        </Link>
      ),
    },
  ];

  const statusOptions = ["all", "active", "pending_review", "draft", "closed"] as const;

  return (
    <>
      {header}
      <div className="space-y-4">
        <KpiRow cols={4}>
          <KpiTile label={t("indexKpiTotal")} value={nf.format(metrics.total)} icon={Briefcase} />
          <KpiTile label={t("indexKpiActive")} value={nf.format(metrics.active)} icon={CheckCircle2} />
          <KpiTile
            label={t("indexKpiPending")}
            value={nf.format(metrics.pending)}
            icon={Clock}
            hint={metrics.pending > 0 ? t("indexKpiPendingHint") : undefined}
          />
          <KpiTile label={t("indexKpiDrafts")} value={nf.format(metrics.drafts)} icon={FileText} />
        </KpiRow>

        <FilterBar
          search={{
            value: search,
            onChange: setSearch,
            placeholder: t("indexSearchPlaceholder"),
            ariaLabel: t("indexSearchPlaceholder"),
          }}
        >
          <div className="flex flex-wrap gap-1.5" role="group" aria-label={tJobs("colStatus")}>
            {statusOptions.map((s) => {
              const activeChip = statusFilter === s;
              return (
                <button
                  key={s}
                  type="button"
                  onClick={() => setStatusFilter(s)}
                  aria-pressed={activeChip}
                  className={
                    activeChip
                      ? "rounded-lg border border-transparent bg-foreground px-3 py-1.5 text-[0.8125rem] font-semibold text-background"
                      : "rounded-lg border border-border bg-card px-3 py-1.5 text-[0.8125rem] font-medium text-muted-foreground transition-colors hover:text-foreground"
                  }
                >
                  {s === "all" ? t("filterAllStatuses") : labels.status(s)}
                </button>
              );
            })}
          </div>
        </FilterBar>

        <DataTable
          columns={columns}
          data={filteredRows}
          getRowId={(job) => job.id}
          loading={query.isPending || !allLoaded}
          globalFilter={search}
          pageSize={12}
          onRowClick={(job) => router.push(`/partner/jobs/${job.id}/applications`)}
          empty={
            <EmptyState
              kind="empty"
              icon={Users}
              title={rows.length === 0 ? t("indexEmptyTitle") : t("noMatchTitle")}
              description={rows.length === 0 ? t("indexEmptyBody") : t("noMatchBody")}
              action={
                rows.length === 0 ? (
                  <Link href="/partner/jobs">
                    <Button variant="primary">{t("goToJobs")}</Button>
                  </Link>
                ) : undefined
              }
            />
          }
        />
      </div>
    </>
  );
}
