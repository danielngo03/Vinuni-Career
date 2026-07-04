"use client";

import { useMemo, useState } from "react";
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
  DownloadSimple,
  Eye,
  Kanban,
  LightbulbFilament,
  MagnifyingGlass,
  Prohibit,
  ShieldWarning,
  SignIn,
  Sparkle,
  UserCircle,
  UserFocus,
  Users,
  WarningCircle,
} from "@phosphor-icons/react";
import { Link } from "@/i18n/navigation";
import { cn } from "@/lib/utils";
import {
  Button,
  DataTable,
  EmptyState,
  Sheet,
  StatusBadge,
  useToast,
  type Column,
} from "@/components/ui";
import { PageHeader } from "@/components/layout/page-header";
import { formatDateTime } from "@/lib/format";
import {
  APPLICATION_STATUS_TONE,
  REVEAL_STATUS_TONE,
  useApplicationLabels,
} from "@/lib/applications/labels";
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
  deriveCandidateInsights,
  MIN_REASON,
  nowIso,
  STAGE_CHIP_ACTIVE,
  STAGE_FILTERS,
  type ForJobData,
} from "./candidates-screen/utils";

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

  const [selectedId, setSelectedId] = useState<string | null>(
    searchParams.get("selected"),
  );
  const [stageFilter, setStageFilter] = useState<string>("all");
  const [revealOpen, setRevealOpen] = useState(false);
  const [reason, setReason] = useState("");
  const [downloading, setDownloading] = useState(false);
  const [exportingCsv, setExportingCsv] = useState(false);

  // Reject modal state (targets one application at a time).
  const [rejectTarget, setRejectTarget] = useState<string | null>(null);
  const [rejectReason, setRejectReason] = useState<RejectionReason | "">("");
  const [rejectNote, setRejectNote] = useState("");
  const [rejectFieldError, setRejectFieldError] = useState<string | null>(null);

  const jobQuery = useQuery({
    queryKey: ["jobs", "owned", jobId, "title"],
    queryFn: () => jobsApi.getOwned(jobId),
    retry: false,
  });

  const forJobKey = useMemo(
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

  const rows: PartnerApplication[] = useMemo(
    () => query.data?.pages.flatMap((p) => p.data) ?? [],
    [query.data],
  );

  const filteredRows: PartnerApplication[] = useMemo(
    () =>
      stageFilter === "all"
        ? rows
        : rows.filter((r) => r.status === stageFilter),
    [rows, stageFilter],
  );

  const candidateInsights = useMemo(
    () => (!query.isPending && !query.isError ? deriveCandidateInsights(rows) : []),
    [rows, query.isPending, query.isError],
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

  /** 409 → friendly "status changed, reloading" toast + refetch. */
  function handleConflict(e: unknown): boolean {
    if (e instanceof ApiError && e.isConflict) {
      toast.show({ tone: "warning", title: t("conflictToast") });
      void qc.invalidateQueries({ queryKey: forJobKey });
      if (selectedId) {
        void qc.invalidateQueries({ queryKey: detailKey(selectedId) });
      }
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
      if (!handleConflict(e)) {
        toast.show({ tone: "error", title: apiError(e) });
      }
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
      // 422 → keep modal open, surface inline "please choose a reason".
      if (e instanceof ApiError && e.isValidation) {
        setRejectFieldError(t("rejectReasonRequired"));
        return;
      }
      closeReject();
      if (!handleConflict(e)) {
        toast.show({ tone: "error", title: apiError(e) });
      }
    },
    onSuccess: (data) => {
      patchCaches(data.id, data);
      qc.setQueryData(detailKey(data.id), data);
      closeReject();
      toast.show({ tone: "success", title: t("rejectedToast") });
    },
  });

  function openReject(id: string) {
    setRejectTarget(id);
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
    rejectMutation.mutate({
      id: rejectTarget,
      reason: rejectReason,
      note: rejectNote,
    });
  }

  const requestReveal = useMutation({
    mutationFn: () =>
      applicationsApi.requestReveal(selectedId as string, reason.trim()),
    onSuccess: () => {
      setRevealOpen(false);
      setReason("");
      toast.show({ tone: "success", title: t("revealRequestedToast") });
      refresh();
    },
    onError: (e) => toast.show({ tone: "error", title: apiError(e) }),
  });

  function refresh() {
    void qc.invalidateQueries({ queryKey: forJobKey });
    if (selectedId) {
      void qc.invalidateQueries({ queryKey: detailKey(selectedId) });
    }
  }

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
      className="mb-4 inline-flex items-center gap-1.5 rounded-lg text-sm font-medium text-[var(--text-secondary)] outline-none hover:text-[var(--text-primary)] focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/30"
    >
      <ArrowLeft aria-hidden weight="bold" className="size-4" />
      {t("backToJobs")}
    </Link>
  );

  /* ---- Permission / auth / not-found gates from the list query ---- */
  if (query.isError && query.error instanceof ApiError) {
    const err = query.error;
    if (err.isPermissionError || err.isAuthError) {
      return (
        <>
          {backLink}
          <EmptyState
            kind={err.isPermissionError ? "permission" : "auth"}
            icon={err.isPermissionError ? ShieldWarning : SignIn}
            title={
              err.isPermissionError
                ? tStates("permissionTitle")
                : tStates("authTitle")
            }
            description={
              err.isPermissionError
                ? tStates("permissionBody")
                : tStates("authBody")
            }
          />
        </>
      );
    }
  }

  const jobTitle = jobQuery.data?.title ?? t("title");

  const columns: Column<PartnerApplication>[] = [
    {
      key: "applicant",
      header: t("colApplicant"),
      cell: (row) => (
        <span className="inline-flex items-center gap-2 font-medium text-[var(--text-primary)]">
          {row.applicant.is_anonymous && !row.applicant.revealed ? (
            <UserFocus
              aria-hidden
              weight="duotone"
              className="size-4 text-[var(--text-muted)]"
            />
          ) : (
            <UserCircle
              aria-hidden
              weight="duotone"
              className="size-4 text-[var(--brand-primary)]"
            />
          )}
          {row.applicant.is_anonymous && !row.applicant.revealed
            ? row.applicant.anonymous_id ?? row.applicant.display_name
            : row.applicant.display_name}
        </span>
      ),
    },
    {
      key: "status",
      header: t("colStatus"),
      cell: (row) => (
        <StatusBadge tone={APPLICATION_STATUS_TONE[row.status] ?? "info"}>
          {labels.status(row.status, row.status_label)}
        </StatusBadge>
      ),
    },
    {
      key: "reveal",
      header: t("colReveal"),
      cell: (row) =>
        row.applicant.is_anonymous ? (
          <StatusBadge tone={REVEAL_STATUS_TONE[row.reveal_status] ?? "draft"}>
            {labels.reveal(row.reveal_status, row.reveal_status_label)}
          </StatusBadge>
        ) : (
          <span className="text-xs text-[var(--text-muted)]">
            {t("identified")}
          </span>
        ),
    },
    {
      key: "applied_at",
      header: t("colApplied"),
      cell: (row) => (
        <span className="text-xs text-[var(--text-secondary)]">
          {formatDateTime(row.applied_at, locale)}
        </span>
      ),
    },
    {
      key: "actions",
      header: "",
      align: "right",
      cell: (row) => (
        <div className="flex items-center justify-end gap-1 whitespace-nowrap">
          {row.status === "submitted" && (
            <Button
              variant="ghost"
              size="sm"
              loading={
                reviewMutation.isPending && reviewMutation.variables === row.id
              }
              onClick={() => reviewMutation.mutate(row.id)}
            >
              <MagnifyingGlass aria-hidden weight="duotone" className="size-4" />
              {t("startReview")}
            </Button>
          )}
          {(row.status === "submitted" || row.status === "under_review") && (
            <Button
              variant="ghost"
              size="sm"
              disabled={
                rejectMutation.isPending && rejectMutation.variables?.id === row.id
              }
              onClick={() => openReject(row.id)}
            >
              <Prohibit aria-hidden weight="duotone" className="size-4" />
              {t("reject")}
            </Button>
          )}
          <Button variant="ghost" size="sm" onClick={() => setSelectedId(row.id)}>
            <Eye aria-hidden weight="duotone" className="size-4" />
            {t("view")}
          </Button>
        </div>
      ),
    },
  ];

  const reasonValid = reason.trim().length >= MIN_REASON;

  return (
    <>
      {backLink}
      <PageHeader
        title={jobTitle}
        description={t("subtitle")}
        actions={
          <div className="flex items-center gap-2">
            <Button
              variant="secondary"
              size="sm"
              onClick={handleExportCsv}
              disabled={exportingCsv}
              aria-label={t("exportCsvAria")}
            >
              <DownloadSimple aria-hidden weight="bold" className="size-4" />
              {exportingCsv ? tc("loading") : t("exportCsv")}
            </Button>
            <Link
              href={`/partner/jobs/${jobId}/pipeline`}
              className="inline-flex items-center gap-1.5 rounded-lg text-sm font-medium text-[var(--text-secondary)] outline-none hover:text-[var(--text-primary)] focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/30"
            >
              <Kanban aria-hidden weight="duotone" className="size-4" />
              {t("viewPipeline")}
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
          {/* Stage filter tab chips */}
          <div className="mb-4 space-y-2">
            <div className="flex flex-wrap gap-2" role="group" aria-label={t("filterStatusLabel")}>
              {STAGE_FILTERS.map((s) => (
                <button
                  key={s}
                  onClick={() => setStageFilter(s)}
                  aria-pressed={stageFilter === s}
                  className={cn(
                    "inline-flex items-center rounded-full border px-3.5 py-1.5 text-xs font-semibold transition-all focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--brand-primary)]",
                    stageFilter === s
                      ? STAGE_CHIP_ACTIVE[s] ?? "border-[var(--brand-primary)]/30 bg-[var(--brand-primary)] text-white shadow-sm"
                      : "border-[var(--border-default)] bg-white text-[var(--text-secondary)] hover:bg-white hover:text-[var(--text-primary)]",
                  )}
                >
                  {s === "all" ? t("filterAllStatuses") : labels.status(s)}
                </button>
              ))}
            </div>
            {!query.isPending && rows.length > 0 && (
              <p className="text-xs font-medium tabular-nums text-[var(--text-muted)]">
                {t("resultCount", { count: filteredRows.length })}
              </p>
            )}
          </div>

          {candidateInsights.length > 0 && (
            <section
              className="mb-4 rounded-2xl border border-[var(--ai-accent)]/25 bg-gradient-to-br from-[var(--ai-accent-soft)] to-white/60 p-4 "
              aria-label={t("aiInsightsTitle")}
            >
              <h2 className="mb-2.5 flex items-center gap-2 text-sm font-bold text-[var(--text-primary)]">
                <span className="flex size-6 shrink-0 items-center justify-center rounded-lg icon-chip-info shadow-sm">
                  <Sparkle aria-hidden weight="duotone" className="size-3.5 text-white" />
                </span>
                {t("aiInsightsTitle")}
              </h2>
              <ul className="space-y-1.5">
                {candidateInsights.map((key) => (
                  <li key={key} className="flex items-start gap-2 text-xs text-[var(--text-secondary)]">
                    <LightbulbFilament aria-hidden weight="duotone" className="mt-0.5 size-3.5 shrink-0 text-[var(--ai-accent)]" />
                    {t(key)}
                  </li>
                ))}
              </ul>
            </section>
          )}

          {!query.isPending && rows.length > 0 && filteredRows.length === 0 ? (
            <EmptyState
              kind="empty"
              icon={Users}
              title={t("noMatchTitle")}
              description={t("noMatchBody")}
              action={
                <Button variant="secondary" onClick={() => setStageFilter("all")}>
                  {t("filterAllStatuses")}
                </Button>
              }
            />
          ) : (
            <DataTable<PartnerApplication>
              columns={columns}
              rows={filteredRows}
              getRowId={(r) => r.id}
              loading={query.isPending}
              caption={t("title")}
              empty={{
                kind: "empty",
                icon: Users,
                title: t("emptyTitle"),
                description: t("emptyBody"),
              }}
            />
          )}

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

      {/* Candidate detail drawer */}
      <Sheet
        open={!!selectedId}
        onClose={() => setSelectedId(null)}
        title={t("detailTitle")}
        closeLabel={tc("close")}
      >
        {detailQuery.isPending ? (
          <p className="text-sm text-[var(--text-muted)]">{tc("loading")}</p>
        ) : detailQuery.isError || !selected ? (
          <EmptyState
            kind="error"
            icon={WarningCircle}
            title={tStates("errorTitle")}
            description={tStates("errorBody")}
            action={
              <Button variant="secondary" onClick={() => detailQuery.refetch()}>
                {tc("retry")}
              </Button>
            }
          />
        ) : (
          <CandidateDetail
            app={selected}
            jobTitle={jobTitle}
            downloading={downloading}
            reviewPending={
              reviewMutation.isPending && reviewMutation.variables === selected.id
            }
            rejectPending={
              rejectMutation.isPending &&
              rejectMutation.variables?.id === selected.id
            }
            onDownload={handleDownload}
            onOpenReveal={() => setRevealOpen(true)}
            onStartReview={() => reviewMutation.mutate(selected.id)}
            onOpenReject={() => openReject(selected.id)}
          />
        )}
      </Sheet>

      {/* Reject decision modal */}
      <RejectModal
        open={!!rejectTarget}
        onClose={closeReject}
        reason={rejectReason}
        onReasonChange={(v) => {
          setRejectReason(v);
          if (v) setRejectFieldError(null);
        }}
        note={rejectNote}
        onNoteChange={setRejectNote}
        fieldError={rejectFieldError}
        loading={rejectMutation.isPending}
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
