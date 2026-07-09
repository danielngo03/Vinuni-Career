"use client";

import * as React from "react";
import { useLocale, useTranslations } from "next-intl";
import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Briefcase,
  Download,
  Copy,
  Eye,
  FileText,
  Kanban,
  ListChecks,
  Plus,
  ShieldAlert,
  Users,
} from "lucide-react";
import { Link } from "@/i18n/navigation";
import { Button } from "@/components/ui";
import {
  DataTable,
  DetailSheet,
  DetailSheetSection,
  EmptyState,
  FilterBar,
  KpiRow,
  KpiTile,
  StatusChip,
  type ChipTone,
  type ColumnDef,
} from "@/components/kit";
import { PageHeader } from "@/components/layout/page-header";
import { cn } from "@/lib/utils";
import { useJobLabels } from "@/lib/jobs/labels";
import { formatLocation } from "@/lib/jobs/format";
import { formatDateShort, formatDateTime, formatDateTimeShort } from "@/lib/format";
import {
  ApiError,
  applicationsApi,
  dashboardsApi,
  jobsApi,
  type JobStatus,
  type OwnerJobSummary,
  type PartnerApplication,
} from "@/lib/api";
import { useToast } from "@/components/ui";
import { useApiErrorMessage } from "@/lib/auth/use-api-error";

const nf = new Intl.NumberFormat();

const STATUS_FILTERS = [
  "all",
  "draft",
  "pending_review",
  "active",
  "rejected",
  "closed",
] as const;

/** Job lifecycle status → soft StatusChip tone (color carries meaning, not decoration). */
const STATUS_TONE: Record<JobStatus, ChipTone> = {
  draft: "neutral",
  pending_review: "warning",
  active: "success",
  rejected: "danger",
  closed: "neutral",
  expired: "neutral",
};

/** JD moderation/quality gate state, derived from lifecycle status. */
function gateFor(status: JobStatus): { key: string; tone: ChipTone } | null {
  switch (status) {
    case "draft":
      return { key: "gatePreSubmit", tone: "amber" };
    case "rejected":
      return { key: "gateRejected", tone: "danger" };
    case "pending_review":
      return { key: "gateInReview", tone: "sky" };
    case "active":
      return { key: "gateCleared", tone: "emerald" };
    default:
      return null;
  }
}

export function PartnerJobsScreen() {
  const t = useTranslations("jobs");
  const tStates = useTranslations("states");
  const tc = useTranslations("common");
  const labels = useJobLabels();
  const qc = useQueryClient();
  const toast = useToast();
  const apiError = useApiErrorMessage();

  const [statusFilter, setStatusFilter] = React.useState<string>("all");
  const [search, setSearch] = React.useState("");
  const [openJobId, setOpenJobId] = React.useState<string | null>(null);

  /* ---- Org-level KPI aggregates (independent of the table filter) ---- */
  const opsQ = useQuery({
    queryKey: ["dashboard", "partner", "ops"],
    queryFn: () => dashboardsApi.partnerOps(),
    retry: false,
    staleTime: 60_000,
  });

  /* ---- Owner job list (server status filter + client search) ---- */
  const listQ = useInfiniteQuery({
    queryKey: ["jobs", "mine", statusFilter],
    queryFn: ({ pageParam }) =>
      jobsApi.listMine({
        cursor: pageParam,
        limit: 20,
        status: statusFilter === "all" ? undefined : statusFilter,
      }),
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.page.next_cursor,
    retry: false,
  });

  const rows: OwnerJobSummary[] = React.useMemo(
    () => listQ.data?.pages.flatMap((p) => p.data) ?? [],
    [listQ.data],
  );

  const duplicateMutation = useMutation({
    mutationFn: (jobId: string) => jobsApi.duplicate(jobId),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["jobs", "mine"] });
      toast.show({ tone: "success", title: t("duplicateSuccess") });
    },
    onError: (e) => toast.show({ tone: "error", title: apiError(e) }),
  });

  /* ---- Bulk actions ---- */
  const bulkCloseMutation = useMutation({
    mutationFn: async (jobs: OwnerJobSummary[]) => {
      const active = jobs.filter((j) => j.status === "active");
      await Promise.allSettled(active.map((j) => jobsApi.close(j.id, j.version)));
      return { closed: active.length, skipped: jobs.length - active.length };
    },
    onSuccess: (r) => {
      void qc.invalidateQueries({ queryKey: ["jobs", "mine"] });
      void qc.invalidateQueries({ queryKey: ["dashboard", "partner", "ops"] });
      toast.show({ tone: "success", title: t("bulkCloseToast", { closed: r.closed, skipped: r.skipped }) });
    },
    onError: (e) => toast.show({ tone: "error", title: apiError(e) }),
  });

  const bulkDuplicateMutation = useMutation({
    mutationFn: async (jobs: OwnerJobSummary[]) => {
      const res = await Promise.allSettled(jobs.map((j) => jobsApi.duplicate(j.id)));
      return res.filter((x) => x.status === "fulfilled").length;
    },
    onSuccess: (count) => {
      void qc.invalidateQueries({ queryKey: ["jobs", "mine"] });
      toast.show({ tone: "success", title: t("bulkDuplicateToast", { count }) });
    },
    onError: (e) => toast.show({ tone: "error", title: apiError(e) }),
  });

  const bulkExportMutation = useMutation({
    mutationFn: async (jobs: OwnerJobSummary[]) => {
      let ok = 0;
      for (const j of jobs) {
        try {
          const blob = await applicationsApi.exportCsv(j.id);
          const url = URL.createObjectURL(blob);
          const a = document.createElement("a");
          a.href = url;
          a.download = `applications-${j.slug || j.id}.csv`;
          document.body.appendChild(a);
          a.click();
          a.remove();
          URL.revokeObjectURL(url);
          ok += 1;
        } catch {
          /* per-job export failure is non-fatal; keep exporting the rest */
        }
      }
      return ok;
    },
    onSuccess: (count) => toast.show({ tone: "success", title: t("bulkExportToast", { count }) }),
    onError: (e) => toast.show({ tone: "error", title: apiError(e) }),
  });

  const newButton = (
    <Link href="/partner/jobs/new">
      <Button variant="primary" size="sm">
        <Plus className="size-4" strokeWidth={2} />
        {t("newJob")}
      </Button>
    </Link>
  );

  const header = (
    <PageHeader title={t("manageTitle")} description={t("manageSubtitle")} actions={newButton} />
  );

  /* ---- Permission / auth gate ---- */
  if (listQ.isError && listQ.error instanceof ApiError) {
    const err = listQ.error;
    if (err.isPermissionError || err.isAuthError) {
      return (
        <>
          {header}
          <EmptyState
            kind={err.isPermissionError ? "permission" : "auth"}
            icon={err.isPermissionError ? ShieldAlert : undefined}
            title={err.isPermissionError ? tStates("permissionTitle") : tStates("authTitle")}
            description={err.isPermissionError ? t("permissionBody") : tStates("authBody")}
          />
        </>
      );
    }
  }

  const columns: ColumnDef<OwnerJobSummary, unknown>[] = [
    {
      accessorKey: "title",
      header: t("colTitle"),
      cell: ({ row }) => {
        const r = row.original;
        return (
          <div className="min-w-0">
            <span className="block truncate font-semibold text-foreground">{r.title}</span>
            <span className="type-caption block truncate text-muted-foreground">
              {labels.employmentType(r.employment_type, r.employment_type_label)}
              {" · "}
              {formatLocation(r.location_city, r.location_country)}
            </span>
          </div>
        );
      },
    },
    {
      accessorKey: "status",
      header: t("colStatus"),
      cell: ({ row }) => (
        <StatusChip tone={STATUS_TONE[row.original.status] ?? "neutral"} dot>
          {labels.status(row.original.status, row.original.status_label)}
        </StatusChip>
      ),
    },
    {
      id: "gate",
      header: t("colGate"),
      enableSorting: false,
      cell: ({ row }) => {
        const gate = gateFor(row.original.status);
        if (!gate) return <span className="text-muted-foreground">—</span>;
        return <StatusChip tone={gate.tone} size="sm">{t(gate.key)}</StatusChip>;
      },
    },
    {
      id: "views",
      header: t("colViews"),
      meta: { align: "right" },
      cell: ({ row }) => (
        <span className="tabular-nums text-foreground">
          {row.original.view_count != null ? nf.format(row.original.view_count) : "—"}
        </span>
      ),
    },
    {
      id: "applies",
      header: t("colApplies"),
      meta: { align: "right" },
      cell: ({ row }) => (
        <span className="tabular-nums text-foreground">
          {row.original.application_count != null ? nf.format(row.original.application_count) : "—"}
        </span>
      ),
    },
    {
      id: "deadline",
      accessorKey: "application_deadline",
      header: t("colDeadline"),
      meta: { align: "right" },
      cell: ({ row }) => {
        const dl = row.original.application_deadline;
        return (
          <span
            className="tabular-nums text-muted-foreground"
            title={dl ? formatDateTimeShort(dl) : undefined}
          >
            {dl ? formatDateShort(dl) : "—"}
          </span>
        );
      },
    },
    {
      id: "actions",
      header: "",
      enableSorting: false,
      meta: { align: "right" },
      cell: ({ row }) => (
        <div className="flex items-center justify-end gap-1" onClick={(e) => e.stopPropagation()}>
          {row.original.status === "active" && (
            <Link href={`/partner/jobs/${row.original.id}/pipeline`}>
              <Button variant="ghost" size="sm">
                <Kanban className="size-4" strokeWidth={1.8} />
                {t("pipeline")}
              </Button>
            </Link>
          )}
          <Link href={`/partner/jobs/${row.original.id}`}>
            <Button variant="ghost" size="sm">{t("manage")}</Button>
          </Link>
        </div>
      ),
    },
  ];

  const ops = opsQ.data?.metrics;
  const total = ops ? ops.jobs_active + ops.jobs_draft + ops.jobs_pending_review : null;

  const listError =
    listQ.isError &&
    !(listQ.error instanceof ApiError && (listQ.error.isPermissionError || listQ.error.isAuthError));

  return (
    <>
      {header}

      <div className="space-y-4">
        {/* KPI row — org-level aggregates */}
        {opsQ.isPending ? (
          <KpiRow cols={4}>
            {Array.from({ length: 4 }).map((_, i) => (
              <div key={i} className="h-[86px] animate-skeleton rounded-xl bg-[var(--bg-muted)]" />
            ))}
          </KpiRow>
        ) : ops ? (
          <KpiRow cols={4}>
            <KpiTile label={t("kpiActive")} value={nf.format(ops.jobs_active)} icon={Briefcase} />
            <KpiTile label={t("kpiDraft")} value={nf.format(ops.jobs_draft)} icon={FileText} />
            <KpiTile
              label={t("kpiPending")}
              value={nf.format(ops.jobs_pending_review)}
              icon={ShieldAlert}
              hint={ops.jobs_pending_review > 0 ? t("kpiPendingHint") : undefined}
            />
            <KpiTile label={t("kpiTotal")} value={total != null ? nf.format(total) : "—"} icon={ListChecks} />
          </KpiRow>
        ) : null}

        {/* Filter bar */}
        <FilterBar
          search={{
            value: search,
            onChange: setSearch,
            placeholder: t("searchPlaceholder"),
            ariaLabel: t("searchPlaceholder"),
          }}
        >
          <div className="flex flex-wrap gap-1.5" role="group" aria-label={t("filterStatusLabel")}>
            {STATUS_FILTERS.map((s) => {
              const active = statusFilter === s;
              return (
                <button
                  key={s}
                  type="button"
                  aria-pressed={active}
                  onClick={() => setStatusFilter(s)}
                  className={cn(
                    "inline-flex items-center rounded-full border px-3 py-1 text-[0.8125rem] font-medium outline-none transition-colors focus-visible:ring-2 focus-visible:ring-[var(--field-focus-border)]",
                    active
                      ? "border-transparent bg-foreground text-[var(--surface-card)]"
                      : "border-border bg-card text-muted-foreground hover:text-foreground",
                  )}
                >
                  {s === "all" ? t("filterAllStatuses") : t(`enums.status.${s}`)}
                </button>
              );
            })}
          </div>
        </FilterBar>

        {/* Table */}
        {listError ? (
          <EmptyState
            kind={listQ.error instanceof ApiError && listQ.error.code === "NETWORK_ERROR" ? "offline" : "error"}
            title={tStates("errorTitle")}
            description={tStates("errorBody")}
            action={
              <Button variant="secondary" onClick={() => listQ.refetch()}>
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
              loading={listQ.isPending}
              globalFilter={search}
              onRowClick={(r) => setOpenJobId(r.id)}
              activeRowId={openJobId ?? undefined}
              enableSelection
              bulkActions={(selected, clear) => (
                <>
                  <Button
                    variant="ghost"
                    size="sm"
                    loading={bulkCloseMutation.isPending}
                    onClick={() => bulkCloseMutation.mutate(selected, { onSuccess: () => clear() })}
                  >
                    <ShieldAlert className="size-4" strokeWidth={1.8} />
                    {t("bulkClose")}
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    loading={bulkDuplicateMutation.isPending}
                    onClick={() => bulkDuplicateMutation.mutate(selected, { onSuccess: () => clear() })}
                  >
                    <Copy className="size-4" strokeWidth={1.8} />
                    {t("bulkDuplicate")}
                  </Button>
                  <Button
                    variant="secondary"
                    size="sm"
                    loading={bulkExportMutation.isPending}
                    onClick={() => bulkExportMutation.mutate(selected)}
                  >
                    <Download className="size-4" strokeWidth={1.8} />
                    {t("bulkExport")}
                  </Button>
                </>
              )}
              empty={
                <EmptyState
                  kind="empty"
                  icon={Briefcase}
                  title={statusFilter === "all" ? t("noJobsTitle") : t("noJobsFilterTitle")}
                  description={statusFilter === "all" ? t("noJobsBody") : t("noJobsFilterBody")}
                  action={statusFilter === "all" ? newButton : undefined}
                />
              }
            />
            {listQ.hasNextPage && (
              <div className="flex justify-center">
                <Button
                  variant="secondary"
                  loading={listQ.isFetchingNextPage}
                  onClick={() => listQ.fetchNextPage()}
                >
                  {tc("loadMore")}
                </Button>
              </div>
            )}
          </>
        )}
      </div>

      <JobDetailSheet
        jobId={openJobId}
        onClose={() => setOpenJobId(null)}
        onDuplicate={(id) => duplicateMutation.mutate(id)}
        duplicating={duplicateMutation.isPending}
      />
    </>
  );
}

/* -------------------------------------------------------------------------- */
/* Detail sheet                                                                */
/* -------------------------------------------------------------------------- */

function JobDetailSheet({
  jobId,
  onClose,
  onDuplicate,
  duplicating,
}: {
  jobId: string | null;
  onClose: () => void;
  onDuplicate: (id: string) => void;
  duplicating: boolean;
}) {
  const t = useTranslations("jobs");
  const tc = useTranslations("common");
  const locale = useLocale();
  const labels = useJobLabels();
  const open = jobId != null;

  const jobQ = useQuery({
    queryKey: ["jobs", "owned", jobId],
    queryFn: () => jobsApi.getOwned(jobId!),
    enabled: open,
    retry: false,
  });

  const applicantsQ = useQuery({
    queryKey: ["jobs", "applicants-glance", jobId],
    queryFn: () => applicationsApi.listForJob(jobId!, { limit: 5 }),
    enabled: open,
    retry: false,
  });

  const job = jobQ.data;
  const applyRate =
    job && job.view_count > 0 && job.application_count >= 0
      ? Math.round((job.application_count / job.view_count) * 100)
      : null;

  return (
    <DetailSheet
      open={open}
      onClose={onClose}
      title={job?.title ?? (jobQ.isPending ? tc("loading") : t("notFoundTitle"))}
      subtitle={
        job
          ? `${labels.employmentType(job.employment_type, job.employment_type_label)} · ${formatLocation(job.location_city, job.location_country)}`
          : undefined
      }
      status={
        job ? (
          <>
            <StatusChip tone={STATUS_TONE[job.status] ?? "neutral"} dot>
              {labels.status(job.status, job.status_label)}
            </StatusChip>
            {job.is_sponsored && <StatusChip tone="amber">{t("sponsored")}</StatusChip>}
          </>
        ) : undefined
      }
      width="lg"
      closeLabel={tc("close")}
      footer={
        job ? (
          <>
            <Button
              variant="ghost"
              size="sm"
              loading={duplicating}
              onClick={() => onDuplicate(job.id)}
            >
              <Copy className="size-4" strokeWidth={1.8} />
              {t("duplicate")}
            </Button>
            <Link href={`/partner/jobs/${job.id}`}>
              <Button variant="primary" size="sm">{t("sheetOpenFull")}</Button>
            </Link>
          </>
        ) : undefined
      }
    >
      {jobQ.isPending ? (
        <div className="space-y-3 p-5">
          <div className="h-20 animate-skeleton rounded-xl bg-[var(--bg-muted)]" />
          <div className="h-32 animate-skeleton rounded-xl bg-[var(--bg-muted)]" />
        </div>
      ) : !job ? (
        <div className="p-5">
          <EmptyState kind="error" title={t("notFoundTitle")} description={t("ownerNotFoundBody")} />
        </div>
      ) : (
        <>
          <DetailSheetSection title={t("sheetMetricsTitle")}>
            <div className="grid grid-cols-3 gap-2.5">
              <MiniMetric icon={Eye} label={t("views")} value={nf.format(job.view_count)} tone="var(--viz-sky)" />
              <MiniMetric icon={Users} label={t("applications")} value={nf.format(job.application_count)} tone="var(--viz-indigo)" />
              <MiniMetric
                icon={ListChecks}
                label={t("statApplyRate")}
                value={applyRate != null ? `${applyRate}%` : "—"}
                tone="var(--viz-emerald)"
              />
            </div>
          </DetailSheetSection>

          <DetailSheetSection
            title={t("sheetApplicantsTitle")}
            action={
              <Link
                href={`/partner/jobs/${job.id}/applications`}
                className="text-[0.8125rem] font-semibold text-[var(--brand-primary)] hover:underline"
              >
                {t("sheetViewAll")}
              </Link>
            }
          >
            {applicantsQ.isPending ? (
              <div className="h-24 animate-skeleton rounded-lg bg-[var(--bg-muted)]" />
            ) : (applicantsQ.data?.data.length ?? 0) === 0 ? (
              <p className="type-small text-muted-foreground">{t("sheetApplicantsEmpty")}</p>
            ) : (
              <ul className="space-y-1.5">
                {applicantsQ.data!.data.slice(0, 5).map((a: PartnerApplication) => (
                  <li key={a.id} className="flex items-center justify-between gap-2">
                    <span className="min-w-0 truncate text-[0.8125rem] font-medium text-foreground">
                      {a.applicant.full_name || "—"}
                    </span>
                    <span className="flex shrink-0 items-center gap-2">
                      <StatusChip tone="neutral" size="sm">{a.status_label}</StatusChip>
                      <span className="type-caption tabular-nums text-muted-foreground">
                        {formatDateTime(a.applied_at, locale)}
                      </span>
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </DetailSheetSection>

          <DetailSheetSection title={t("sheetLinksTitle")}>
            <div className="flex flex-wrap gap-2">
              {job.status === "active" && (
                <Link href={`/jobs/${job.id}`} target="_blank">
                  <Button variant="secondary" size="sm">
                    <Eye className="size-4" strokeWidth={1.8} />
                    {t("viewLive")}
                  </Button>
                </Link>
              )}
              <Link href={`/partner/jobs/${job.id}/pipeline`}>
                <Button variant="secondary" size="sm">
                  <Kanban className="size-4" strokeWidth={1.8} />
                  {t("viewPipeline")}
                </Button>
              </Link>
            </div>
          </DetailSheetSection>
        </>
      )}
    </DetailSheet>
  );
}

function MiniMetric({
  icon: Icon,
  label,
  value,
  tone,
}: {
  icon: React.ElementType;
  label: string;
  value: string;
  tone: string;
}) {
  return (
    <div className="rounded-xl border border-border bg-[var(--bg-subtle)] p-3">
      <span
        className="flex size-7 items-center justify-center rounded-lg"
        style={{ background: `color-mix(in oklch, ${tone} 14%, transparent)` }}
      >
        <Icon aria-hidden className="size-4" strokeWidth={1.9} style={{ color: tone }} />
      </span>
      <p className="type-metric mt-2 text-foreground">{value}</p>
      <p className="type-caption mt-0.5 truncate text-muted-foreground">{label}</p>
    </div>
  );
}
