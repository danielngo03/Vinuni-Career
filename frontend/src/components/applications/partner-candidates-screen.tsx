"use client";

import * as React from "react";
import { useSearchParams } from "next/navigation";
import { useLocale, useTranslations } from "next-intl";
import {
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import {
  ArrowLeft,
  CheckCheck,
  Download,
  Eye,
  EyeOff,
  Inbox,
  Kanban,
  Loader2,
  BadgeCheck,
  Search,
  Ban,
  ShieldAlert,
  LogIn,
  Users2,
} from "lucide-react";
import { Link } from "@/i18n/navigation";
import { Button, useToast } from "@/components/ui";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { MessageCandidateButton } from "@/components/messaging/message-candidate-button";
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
} from "@/components/kit";
import { formatDateTime } from "@/lib/format";
import { useApplicationLabels } from "@/lib/applications/labels";
import {
  ApiError,
  applicationsApi,
  jobsApi,
  resolveDownloadUrl,
  type PartnerApplication,
  type RejectionReason,
} from "@/lib/api";
import { useApiErrorMessage } from "@/lib/auth/use-api-error";
import { CandidateDetail } from "./candidates-screen/candidate-detail";
import { RejectModal } from "./candidates-screen/reject-modal";
import { RevealModal } from "./candidates-screen/reveal-modal";
import {
  MIN_REASON,
  nowIso,
  STAGE_FILTERS,
  type ForJobData,
} from "./candidates-screen/utils";
import {
  APPLICATION_STATUS_CHIP,
  REVEAL_STATUS_CHIP,
  initials,
} from "./chip-tones";

const nf = new Intl.NumberFormat();

type RejectTarget =
  | { kind: "single"; id: string }
  | { kind: "bulk"; ids: string[]; clear: () => void };

export function PartnerCandidatesScreen({ jobId }: { jobId: string }) {
  const t = useTranslations("candidates");
  const tStates = useTranslations("states");
  const tc = useTranslations("common");
  const locale = useLocale();
  const labels = useApplicationLabels();
  const toast = useToast();
  const qc = useQueryClient();
  const apiError = useApiErrorMessage();
  const searchParams = useSearchParams();

  const [selectedId, setSelectedId] = React.useState<string | null>(
    searchParams.get("selected"),
  );
  const [search, setSearch] = React.useState("");
  const [statusFilter, setStatusFilter] = React.useState<string>("all");
  const [revealOpen, setRevealOpen] = React.useState(false);
  const [reason, setReason] = React.useState("");
  const [downloading, setDownloading] = React.useState(false);
  const [exportingCsv, setExportingCsv] = React.useState(false);

  // Reject modal (single row OR bulk selection).
  const [rejectTarget, setRejectTarget] = React.useState<RejectTarget | null>(null);
  const [rejectReason, setRejectReason] = React.useState<RejectionReason | "">("");
  const [rejectNote, setRejectNote] = React.useState("");
  const [rejectFieldError, setRejectFieldError] = React.useState<string | null>(null);

  const jobQuery = useQuery({
    queryKey: ["jobs", "owned", jobId, "title"],
    queryFn: () => jobsApi.getOwned(jobId),
    retry: false,
  });

  const forJobKey = React.useMemo(
    () => ["applications", "forJob", jobId] as const,
    [jobId],
  );

  const query = useInfiniteQuery({
    queryKey: forJobKey,
    queryFn: ({ pageParam }) =>
      applicationsApi.listForJob(jobId, { cursor: pageParam, limit: 20 }),
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.page.next_cursor,
    retry: false,
  });

  // Auto-load the full set (bounded) so KPI counts + client filtering are honest.
  const pageCount = query.data?.pages.length ?? 0;
  React.useEffect(() => {
    if (query.hasNextPage && !query.isFetchingNextPage && pageCount < 50) {
      void query.fetchNextPage();
    }
  }, [query.hasNextPage, query.isFetchingNextPage, pageCount, query]);

  const allLoaded = !query.hasNextPage || pageCount >= 50;

  const rows: PartnerApplication[] = React.useMemo(
    () => query.data?.pages.flatMap((p) => p.data) ?? [],
    [query.data],
  );

  const metrics = React.useMemo(() => {
    const submitted = rows.filter((r) => r.status === "submitted").length;
    const underReview = rows.filter((r) => r.status === "under_review").length;
    const hired = rows.filter((r) => r.status === "hired").length;
    return { total: rows.length, submitted, underReview, hired };
  }, [rows]);

  const filteredRows: PartnerApplication[] = React.useMemo(
    () =>
      statusFilter === "all" ? rows : rows.filter((r) => r.status === statusFilter),
    [rows, statusFilter],
  );

  const detailQuery = useQuery({
    queryKey: ["applications", "partnerDetail", selectedId],
    queryFn: () => applicationsApi.getForPartner(selectedId as string),
    enabled: !!selectedId,
    retry: false,
  });

  const selected = detailQuery.data;
  const detailKey = (id: string) =>
    ["applications", "partnerDetail", id] as const;

  /* ----------------------- optimistic cache helpers ----------------------- */

  function patchCaches(id: string, patch: Partial<PartnerApplication>) {
    qc.setQueryData<ForJobData>(forJobKey, (old) =>
      old
        ? {
            ...old,
            pages: old.pages.map((pg) => ({
              ...pg,
              data: pg.data.map((r) => (r.id === id ? { ...r, ...patch } : r)),
            })),
          }
        : old,
    );
    qc.setQueryData<PartnerApplication>(detailKey(id), (old) =>
      old ? { ...old, ...patch } : old,
    );
  }

  function snapshot(id: string) {
    return {
      id,
      list: qc.getQueryData<ForJobData>(forJobKey),
      detail: qc.getQueryData<PartnerApplication>(detailKey(id)),
    };
  }

  function restore(ctx: ReturnType<typeof snapshot>) {
    if (ctx.list) qc.setQueryData(forJobKey, ctx.list);
    qc.setQueryData(detailKey(ctx.id), ctx.detail);
  }

  function invalidateList() {
    void qc.invalidateQueries({ queryKey: forJobKey });
  }

  /** 409 → friendly "status changed, reloading" toast + refetch. */
  function handleConflict(e: unknown): boolean {
    if (e instanceof ApiError && e.isConflict) {
      toast.show({ tone: "warning", title: t("conflictToast") });
      invalidateList();
      if (selectedId) void qc.invalidateQueries({ queryKey: detailKey(selectedId) });
      return true;
    }
    return false;
  }

  /* ------------------------------ mutations ------------------------------- */

  const reviewMutation = useMutation({
    mutationFn: (id: string) => applicationsApi.review(id),
    onMutate: async (id) => {
      await qc.cancelQueries({ queryKey: forJobKey });
      const ctx = snapshot(id);
      patchCaches(id, { status: "under_review", last_status_at: nowIso() });
      return ctx;
    },
    onError: (e, _id, ctx) => {
      if (ctx) restore(ctx);
      if (!handleConflict(e)) toast.show({ tone: "error", title: apiError(e) });
    },
    onSuccess: (data) => {
      patchCaches(data.id, data);
      qc.setQueryData(detailKey(data.id), data);
      toast.show({ tone: "success", title: t("reviewStartedToast") });
    },
  });

  const rejectMutation = useMutation({
    mutationFn: (vars: { id: string; reason: RejectionReason; note: string }) =>
      applicationsApi.reject(vars.id, {
        reason: vars.reason,
        note: vars.note.trim() || undefined,
      }),
    onMutate: async (vars) => {
      await qc.cancelQueries({ queryKey: forJobKey });
      const ctx = snapshot(vars.id);
      patchCaches(vars.id, {
        status: "rejected",
        rejection_reason: vars.reason,
        rejection_note: vars.note.trim() || null,
        last_status_at: nowIso(),
      });
      return ctx;
    },
    onError: (e, _vars, ctx) => {
      if (ctx) restore(ctx);
      if (e instanceof ApiError && e.isValidation) {
        setRejectFieldError(t("rejectReasonRequired"));
        return;
      }
      closeReject();
      if (!handleConflict(e)) toast.show({ tone: "error", title: apiError(e) });
    },
    onSuccess: (data) => {
      patchCaches(data.id, data);
      qc.setQueryData(detailKey(data.id), data);
      closeReject();
      toast.show({ tone: "success", title: t("rejectedToast") });
    },
  });

  const bulkReviewMutation = useMutation({
    mutationFn: (ids: string[]) => applicationsApi.bulkReview(jobId, ids),
    onSuccess: (res) => {
      invalidateList();
      toast.show({ tone: "success", title: t("bulkReviewedToast", { count: res.reviewed }) });
    },
    onError: (e) => toast.show({ tone: "error", title: apiError(e) }),
  });

  const bulkRejectMutation = useMutation({
    mutationFn: (vars: { ids: string[]; reason: RejectionReason; note: string }) =>
      applicationsApi.bulkReject(jobId, {
        application_ids: vars.ids,
        reason: vars.reason,
        note: vars.note.trim() || undefined,
      }),
    onError: (e) => {
      if (e instanceof ApiError && e.isValidation) {
        setRejectFieldError(t("rejectReasonRequired"));
        return;
      }
      closeReject();
      toast.show({ tone: "error", title: apiError(e) });
    },
    onSuccess: (res) => {
      closeReject();
      invalidateList();
      toast.show({ tone: "success", title: t("bulkRejectedToast", { count: res.rejected }) });
    },
  });

  function openRejectSingle(id: string) {
    setRejectTarget({ kind: "single", id });
    setRejectReason("");
    setRejectNote("");
    setRejectFieldError(null);
  }

  function openRejectBulk(ids: string[], clear: () => void) {
    setRejectTarget({ kind: "bulk", ids, clear });
    setRejectReason("");
    setRejectNote("");
    setRejectFieldError(null);
  }

  function closeReject() {
    setRejectTarget(null);
    setRejectReason("");
    setRejectNote("");
    setRejectFieldError(null);
  }

  function submitReject() {
    if (!rejectTarget) return;
    if (!rejectReason) {
      setRejectFieldError(t("rejectReasonRequired"));
      return;
    }
    if (rejectTarget.kind === "single") {
      rejectMutation.mutate({ id: rejectTarget.id, reason: rejectReason, note: rejectNote });
    } else {
      rejectTarget.clear();
      bulkRejectMutation.mutate({ ids: rejectTarget.ids, reason: rejectReason, note: rejectNote });
    }
  }

  const requestReveal = useMutation({
    mutationFn: () => applicationsApi.requestReveal(selectedId as string, reason.trim()),
    onSuccess: () => {
      setRevealOpen(false);
      setReason("");
      toast.show({ tone: "success", title: t("revealRequestedToast") });
      invalidateList();
      if (selectedId) void qc.invalidateQueries({ queryKey: detailKey(selectedId) });
    },
    onError: (e) => toast.show({ tone: "error", title: apiError(e) }),
  });

  async function handleDownload() {
    if (!selectedId) return;
    setDownloading(true);
    try {
      const info = await applicationsApi.getCvDownload(selectedId);
      window.open(resolveDownloadUrl(info.download_url), "_blank", "noopener");
      toast.show({ tone: "success", title: t("downloadStarted") });
    } catch (e) {
      toast.show({ tone: "error", title: apiError(e) });
    } finally {
      setDownloading(false);
    }
  }

  async function handleExportCsv() {
    setExportingCsv(true);
    try {
      const blob = await applicationsApi.exportCsv(jobId);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `applications_${jobId}.csv`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
      toast.show({ tone: "success", title: t("exportCsvSuccess") });
    } catch (e) {
      toast.show({ tone: "error", title: apiError(e) });
    } finally {
      setExportingCsv(false);
    }
  }

  const backLink = (
    <Link
      href="/partner/candidates"
      className="mb-4 inline-flex items-center gap-1.5 rounded-lg type-small font-medium text-muted-foreground outline-none hover:text-foreground focus-visible:ring-2 focus-visible:ring-[var(--field-focus-border)]"
    >
      <ArrowLeft aria-hidden className="size-4" strokeWidth={1.8} />
      {t("backToJobs")}
    </Link>
  );

  /* ---- Permission / auth gates from the list query ---- */
  if (query.isError && query.error instanceof ApiError) {
    const err = query.error;
    if (err.isPermissionError || err.isAuthError) {
      return (
        <>
          {backLink}
          <EmptyState
            kind={err.isPermissionError ? "permission" : "auth"}
            icon={err.isPermissionError ? ShieldAlert : LogIn}
            title={err.isPermissionError ? tStates("permissionTitle") : tStates("authTitle")}
            description={err.isPermissionError ? tStates("permissionBody") : tStates("authBody")}
          />
        </>
      );
    }
  }

  const jobTitle = jobQuery.data?.title ?? t("title");

  const columns: ColumnDef<PartnerApplication, unknown>[] = [
    {
      id: "applicant",
      accessorFn: (r) =>
        r.applicant.is_anonymous && !r.applicant.revealed
          ? r.applicant.anonymous_id ?? r.applicant.display_name
          : r.applicant.display_name,
      header: t("colApplicant"),
      cell: ({ row }) => {
        const a = row.original.applicant;
        const anon = a.is_anonymous && !a.revealed;
        const name = anon ? a.anonymous_id ?? a.display_name : a.display_name;
        return (
          <span className="inline-flex min-w-0 items-center gap-2.5">
            <Avatar size="sm">
              <AvatarFallback className={anon ? "bg-[var(--bg-muted)] text-muted-foreground" : undefined}>
                {anon ? <EyeOff aria-hidden className="size-3" strokeWidth={1.8} /> : initials(name)}
              </AvatarFallback>
            </Avatar>
            <span className="min-w-0">
              <span className="block truncate font-medium text-foreground">{name}</span>
              {anon && (
                <span className="block type-caption text-muted-foreground">{t("anonymousShort")}</span>
              )}
            </span>
          </span>
        );
      },
    },
    {
      id: "status",
      accessorFn: (r) => r.status,
      header: t("colStatus"),
      cell: ({ row }) => (
        <StatusChip tone={APPLICATION_STATUS_CHIP[row.original.status] ?? "neutral"}>
          {labels.status(row.original.status, row.original.status_label)}
        </StatusChip>
      ),
    },
    {
      id: "reveal",
      enableSorting: false,
      header: t("colReveal"),
      cell: ({ row }) =>
        row.original.applicant.is_anonymous ? (
          <StatusChip tone={REVEAL_STATUS_CHIP[row.original.reveal_status] ?? "neutral"}>
            {labels.reveal(row.original.reveal_status, row.original.reveal_status_label)}
          </StatusChip>
        ) : (
          <span className="type-caption text-muted-foreground">{t("identified")}</span>
        ),
    },
    {
      id: "applied_at",
      accessorFn: (r) => r.applied_at,
      header: t("colApplied"),
      cell: ({ row }) => (
        <span className="type-caption tabular-nums text-muted-foreground">
          {formatDateTime(row.original.applied_at, locale)}
        </span>
      ),
    },
    {
      id: "actions",
      enableSorting: false,
      meta: { align: "right" },
      header: "",
      cell: ({ row }) => (
        <div className="flex items-center justify-end gap-1 whitespace-nowrap">
          {row.original.status === "submitted" && (
            <Button
              variant="ghost"
              size="sm"
              loading={reviewMutation.isPending && reviewMutation.variables === row.original.id}
              onClick={(e) => {
                e.stopPropagation();
                reviewMutation.mutate(row.original.id);
              }}
            >
              <Search aria-hidden className="size-4" strokeWidth={1.8} />
              {t("startReview")}
            </Button>
          )}
          <Button
            variant="ghost"
            size="sm"
            onClick={(e) => {
              e.stopPropagation();
              setSelectedId(row.original.id);
            }}
          >
            <Eye aria-hidden className="size-4" strokeWidth={1.8} />
            {t("view")}
          </Button>
        </div>
      ),
    },
  ];

  const reasonValid = reason.trim().length >= MIN_REASON;

  const selApplicant = selected?.applicant;
  const selAnon = !!selApplicant && selApplicant.is_anonymous && !selApplicant.revealed;
  const selName = selApplicant
    ? selAnon
      ? selApplicant.anonymous_id ?? selApplicant.display_name
      : selApplicant.display_name
    : t("detailTitle");
  const canReview = selected?.status === "submitted";
  const canReject = selected?.status === "submitted" || selected?.status === "under_review";

  return (
    <>
      {backLink}
      <PageHeader
        title={jobTitle}
        subtitle={t("subtitle")}
        actions={
          <div className="flex items-center gap-2">
            <Button
              variant="secondary"
              size="sm"
              onClick={handleExportCsv}
              disabled={exportingCsv}
              aria-label={t("exportCsvAria")}
            >
              <Download aria-hidden className="size-4" strokeWidth={1.8} />
              {exportingCsv ? tc("loading") : t("exportCsv")}
            </Button>
            <Link href={`/partner/jobs/${jobId}/pipeline`}>
              <Button variant="secondary" size="sm">
                <Kanban aria-hidden className="size-4" strokeWidth={1.8} />
                {t("viewPipeline")}
              </Button>
            </Link>
          </div>
        }
      />

      {query.isError &&
      query.error instanceof ApiError &&
      !query.error.isPermissionError &&
      !query.error.isAuthError ? (
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
        <div className="space-y-4">
          <KpiRow cols={4}>
            <KpiTile label={t("kpiTotal")} value={nf.format(metrics.total)} icon={Users2} />
            <KpiTile
              label={t("kpiToReview")}
              value={nf.format(metrics.submitted)}
              icon={Inbox}
              hint={metrics.submitted > 0 ? t("kpiToReviewHint") : undefined}
            />
            <KpiTile label={t("kpiUnderReview")} value={nf.format(metrics.underReview)} icon={Search} />
            <KpiTile label={t("kpiHired")} value={nf.format(metrics.hired)} icon={BadgeCheck} />
          </KpiRow>

          <FilterBar
            search={{
              value: search,
              onChange: setSearch,
              placeholder: t("searchPlaceholder"),
              ariaLabel: t("searchPlaceholder"),
            }}
            actions={
              !allLoaded && !query.isPending ? (
                <span className="inline-flex items-center gap-1.5 type-caption text-muted-foreground">
                  <Loader2 aria-hidden className="size-3.5 animate-spin" strokeWidth={2} />
                  {tc("loading")}
                </span>
              ) : rows.length > 0 ? (
                <span className="type-caption tabular-nums text-muted-foreground">
                  {t("resultCount", { count: filteredRows.length })}
                </span>
              ) : undefined
            }
          >
            <div className="flex flex-wrap gap-1.5" role="group" aria-label={t("filterStatusLabel")}>
              {STAGE_FILTERS.map((s) => {
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
            getRowId={(r) => r.id}
            loading={query.isPending}
            globalFilter={search}
            pageSize={12}
            enableSelection
            activeRowId={selectedId ?? undefined}
            onRowClick={(r) => setSelectedId(r.id)}
            bulkActions={(sel, clear) => {
              const reviewable = sel.filter((r) => r.status === "submitted").map((r) => r.id);
              const rejectable = sel
                .filter((r) => r.status === "submitted" || r.status === "under_review")
                .map((r) => r.id);
              return (
                <>
                  <Button
                    variant="secondary"
                    size="sm"
                    disabled={reviewable.length === 0 || bulkReviewMutation.isPending}
                    onClick={() => {
                      bulkReviewMutation.mutate(reviewable);
                      clear();
                    }}
                  >
                    <CheckCheck aria-hidden className="size-4" strokeWidth={1.8} />
                    {t("bulkReviewCta")}
                  </Button>
                  <Button
                    variant="danger"
                    size="sm"
                    disabled={rejectable.length === 0}
                    onClick={() => openRejectBulk(rejectable, clear)}
                  >
                    <Ban aria-hidden className="size-4" strokeWidth={1.8} />
                    {t("bulkRejectCta")}
                  </Button>
                </>
              );
            }}
            empty={
              <EmptyState
                kind="empty"
                icon={Users2}
                title={rows.length === 0 ? t("emptyTitle") : t("noMatchTitle")}
                description={rows.length === 0 ? t("emptyBody") : t("noMatchBody")}
                action={
                  rows.length > 0 ? (
                    <Button
                      variant="secondary"
                      onClick={() => {
                        setStatusFilter("all");
                        setSearch("");
                      }}
                    >
                      {t("filterAllStatuses")}
                    </Button>
                  ) : undefined
                }
              />
            }
          />
        </div>
      )}

      {/* Candidate detail drawer */}
      <DetailSheet
        open={!!selectedId}
        onClose={() => setSelectedId(null)}
        width="lg"
        closeLabel={tc("close")}
        title={selName}
        subtitle={
          selected
            ? selAnon
              ? t("anonymousShort")
              : selected.applicant.email ?? jobTitle
            : undefined
        }
        avatar={
          selected ? (
            <Avatar size="lg">
              <AvatarFallback className={selAnon ? "bg-[var(--bg-muted)] text-muted-foreground" : undefined}>
                {selAnon ? <EyeOff aria-hidden className="size-4" strokeWidth={1.8} /> : initials(selName)}
              </AvatarFallback>
            </Avatar>
          ) : undefined
        }
        status={
          selected ? (
            <>
              <StatusChip tone={APPLICATION_STATUS_CHIP[selected.status] ?? "neutral"}>
                {labels.status(selected.status, selected.status_label)}
              </StatusChip>
              {selected.applicant.is_anonymous && (
                <StatusChip tone={REVEAL_STATUS_CHIP[selected.reveal_status] ?? "neutral"}>
                  {labels.reveal(selected.reveal_status, selected.reveal_status_label)}
                </StatusChip>
              )}
            </>
          ) : undefined
        }
        headerActions={selected ? <MessageCandidateButton applicationId={selected.id} /> : undefined}
        footer={
          selected && (canReview || canReject) ? (
            <>
              {canReject && (
                <Button
                  variant="danger"
                  size="sm"
                  disabled={
                    (reviewMutation.isPending && reviewMutation.variables === selected.id) ||
                    (rejectMutation.isPending && rejectMutation.variables?.id === selected.id)
                  }
                  onClick={() => openRejectSingle(selected.id)}
                >
                  <Ban aria-hidden className="size-4" strokeWidth={1.8} />
                  {t("reject")}
                </Button>
              )}
              {canReview && (
                <Button
                  variant="primary"
                  size="sm"
                  loading={reviewMutation.isPending && reviewMutation.variables === selected.id}
                  onClick={() => reviewMutation.mutate(selected.id)}
                >
                  <Search aria-hidden className="size-4" strokeWidth={1.8} />
                  {t("startReview")}
                </Button>
              )}
            </>
          ) : undefined
        }
      >
        {detailQuery.isPending ? (
          <div className="space-y-3 p-5">
            <div className="h-20 animate-skeleton rounded-xl bg-[var(--bg-muted)]" />
            <div className="h-40 animate-skeleton rounded-xl bg-[var(--bg-muted)]" />
          </div>
        ) : detailQuery.isError || !selected ? (
          <div className="p-5">
            <EmptyState
              kind="error"
              title={tStates("errorTitle")}
              description={tStates("errorBody")}
              action={
                <Button variant="secondary" onClick={() => detailQuery.refetch()}>
                  {tc("retry")}
                </Button>
              }
            />
          </div>
        ) : (
          <CandidateDetail
            app={selected}
            jobTitle={jobTitle}
            downloading={downloading}
            onDownload={handleDownload}
            onOpenReveal={() => setRevealOpen(true)}
          />
        )}
      </DetailSheet>

      {/* Reject decision modal (single or bulk) */}
      <RejectModal
        open={!!rejectTarget}
        count={rejectTarget?.kind === "bulk" ? rejectTarget.ids.length : 1}
        onClose={closeReject}
        reason={rejectReason}
        onReasonChange={(v) => {
          setRejectReason(v);
          if (v) setRejectFieldError(null);
        }}
        note={rejectNote}
        onNoteChange={setRejectNote}
        fieldError={rejectFieldError}
        loading={rejectMutation.isPending || bulkRejectMutation.isPending}
        onSubmit={submitReject}
      />

      {/* Reveal request modal */}
      <RevealModal
        open={revealOpen}
        onClose={() => {
          setRevealOpen(false);
          setReason("");
        }}
        reason={reason}
        onReasonChange={setReason}
        reasonValid={reasonValid}
        minReason={MIN_REASON}
        loading={requestReveal.isPending}
        onSubmit={() => requestReveal.mutate()}
      />
    </>
  );
}
