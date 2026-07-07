"use client";

import { useEffect, useMemo, useRef, useState } from "react";
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
  CaretDown,
  CaretLeft,
  CaretRight,
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
  SegmentedControl,
  Sheet,
  Skeleton,
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
  type ApplicantRankingItem,
  type PartnerApplication,
  type RejectionReason,
} from "@/lib/api";
import { useApiErrorMessage } from "@/lib/auth/use-api-error";
import { CandidateDetail } from "./candidates-screen/candidate-detail";
import { FitChip } from "./candidates-screen/fit-chip";
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

type SortMode = "newest" | "best";

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
  const [sort, setSort] = useState<SortMode>("newest");
  const [fitExpanded, setFitExpanded] = useState<Set<string>>(new Set());
  const [revealOpen, setRevealOpen] = useState(false);
  const [reason, setReason] = useState("");
  const [downloading, setDownloading] = useState(false);
  const [exportingCsv, setExportingCsv] = useState(false);

  // Prev/Next pager focus management for the review drawer.
  const prevBtnRef = useRef<HTMLButtonElement>(null);
  const nextBtnRef = useRef<HTMLButtonElement>(null);
  const lastDirRef = useRef<"prev" | "next" | null>(null);

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

  /* --------------------------- fit ranking (advisory) --------------------- */
  // Fetched when the recruiter switches to "Best match" OR opens the drawer (so
  // the review drawer can surface the same fit chip). Advisory triage only.
  const rankingEnabled = sort === "best" || !!selectedId;
  const rankingQuery = useQuery({
    queryKey: ["applications", "ranking", jobId],
    queryFn: () => applicationsApi.rankApplicants(jobId),
    enabled: rankingEnabled,
    staleTime: 60 * 1000,
    retry: false,
  });

  const fitByAppId = useMemo(() => {
    const m = new Map<string, ApplicantRankingItem>();
    for (const it of rankingQuery.data?.items ?? []) m.set(it.application_id, it);
    return m;
  }, [rankingQuery.data]);

  const rankingSignal = rankingQuery.data?.signal;

  // "Best match" reorders the CURRENTLY LOADED, filtered rows by server rank.
  // Falls back to the newest order while ranking is pending/errored (no fake data).
  const displayedRows: PartnerApplication[] = useMemo(() => {
    if (sort !== "best" || !rankingQuery.data) return filteredRows;
    const rankOf = (id: string) =>
      fitByAppId.get(id)?.rank ?? Number.POSITIVE_INFINITY;
    return [...filteredRows].sort((a, b) => rankOf(a.id) - rankOf(b.id));
  }, [filteredRows, sort, rankingQuery.data, fitByAppId]);

  function toggleFitExpanded(id: string) {
    setFitExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  /* ------------------------------ drawer pager ---------------------------- */
  const orderedForNav = displayedRows;
  const selectedIndex = selectedId
    ? orderedForNav.findIndex((r) => r.id === selectedId)
    : -1;
  const hasPrev = selectedIndex > 0;
  const hasNext =
    selectedIndex >= 0 && selectedIndex < orderedForNav.length - 1;

  function goTo(dir: "prev" | "next") {
    if (selectedIndex < 0) return;
    const nextIdx = dir === "prev" ? selectedIndex - 1 : selectedIndex + 1;
    const nextRow = orderedForNav[nextIdx];
    if (!nextRow) return;
    lastDirRef.current = dir;
    setSelectedId(nextRow.id);
  }

  // Left/Right arrows page through the drawer, unless focus is in a text field.
  useEffect(() => {
    if (!selectedId) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
      const el = document.activeElement as HTMLElement | null;
      const tag = el?.tagName;
      if (
        tag === "INPUT" ||
        tag === "TEXTAREA" ||
        tag === "SELECT" ||
        el?.isContentEditable
      ) {
        return;
      }
      const idx = orderedForNav.findIndex((r) => r.id === selectedId);
      if (idx < 0) return;
      const nextIdx = e.key === "ArrowLeft" ? idx - 1 : idx + 1;
      const nextRow = orderedForNav[nextIdx];
      if (!nextRow) return;
      e.preventDefault();
      lastDirRef.current = e.key === "ArrowLeft" ? "prev" : "next";
      setSelectedId(nextRow.id);
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [selectedId, orderedForNav]);

  // Keep keyboard focus on a pager control after paging (never drop it — if the
  // used control becomes disabled at an edge, fall back to its sibling).
  useEffect(() => {
    const dir = lastDirRef.current;
    if (!dir) return;
    lastDirRef.current = null;
    const primary = dir === "next" ? nextBtnRef.current : prevBtnRef.current;
    const secondary = dir === "next" ? prevBtnRef.current : nextBtnRef.current;
    if (primary && !primary.disabled) primary.focus();
    else secondary?.focus();
  }, [selectedId]);

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

  const applicantCol: Column<PartnerApplication> = {
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
  };

  const fitCol: Column<PartnerApplication> = {
    key: "fit",
    header: t("fitColHeader"),
    cell: (row) => {
      if (rankingQuery.isPending) {
        return <Skeleton className="h-5 w-24" />;
      }
      const item = fitByAppId.get(row.id);
      if (!item) {
        return <span className="text-xs text-[var(--text-muted)]">—</span>;
      }
      const expanded = fitExpanded.has(row.id);
      const hasWhy = item.matched_skills.length > 0 || item.gaps.length > 0;
      return (
        <div className="flex flex-col gap-1">
          <div className="flex flex-wrap items-center gap-2">
            <FitChip score={item.fit_score} band={item.fit_band} />
            {item.stale && (
              <span
                className="inline-flex items-center text-[var(--amber-700)]"
                title={t("fitStale")}
              >
                <WarningCircle aria-hidden weight="duotone" className="size-3.5" />
                <span className="sr-only">{t("fitStale")}</span>
              </span>
            )}
            {hasWhy && (
              <button
                type="button"
                aria-expanded={expanded}
                onClick={() => toggleFitExpanded(row.id)}
                className="inline-flex items-center gap-0.5 rounded text-[11px] font-medium text-[var(--text-secondary)] outline-none hover:text-[var(--text-primary)] focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/30"
              >
                {t("fitWhy")}
                <CaretDown
                  aria-hidden
                  weight="bold"
                  className={cn(
                    "size-3 transition-transform",
                    expanded && "rotate-180",
                  )}
                />
              </button>
            )}
          </div>
          {expanded && hasWhy && (
            <div className="max-w-[280px] space-y-1.5 pt-0.5">
              {item.matched_skills.length > 0 && (
                <div className="flex flex-wrap items-center gap-1">
                  <span className="text-[10px] font-semibold uppercase tracking-wide text-[var(--text-muted)]">
                    {t("fitMatchedLabel")}
                  </span>
                  {item.matched_skills.map((s) => (
                    <span
                      key={s}
                      className="inline-flex items-center rounded-full border border-emerald-200 bg-emerald-50 px-1.5 py-0.5 text-[10px] font-medium text-emerald-700"
                    >
                      {s}
                    </span>
                  ))}
                </div>
              )}
              {item.gaps.length > 0 && (
                <div className="flex flex-wrap items-center gap-1">
                  <span className="text-[10px] font-semibold uppercase tracking-wide text-[var(--text-muted)]">
                    {t("fitGapsLabel")}
                  </span>
                  {item.gaps.map((s) => (
                    <span
                      key={s}
                      className="inline-flex items-center rounded-full border border-[var(--border-default)] bg-[var(--bg-subtle)] px-1.5 py-0.5 text-[10px] font-medium text-[var(--text-secondary)]"
                    >
                      {s}
                    </span>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      );
    },
  };

  const statusCol: Column<PartnerApplication> = {
    key: "status",
    header: t("colStatus"),
    cell: (row) => (
      <StatusBadge tone={APPLICATION_STATUS_TONE[row.status] ?? "info"}>
        {labels.status(row.status, row.status_label)}
      </StatusBadge>
    ),
  };

  const revealCol: Column<PartnerApplication> = {
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
  };

  const appliedCol: Column<PartnerApplication> = {
    key: "applied_at",
    header: t("colApplied"),
    cell: (row) => (
      <span className="text-xs text-[var(--text-secondary)]">
        {formatDateTime(row.applied_at, locale)}
      </span>
    ),
  };

  const actionsCol: Column<PartnerApplication> = {
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
  };

  const columns: Column<PartnerApplication>[] = [
    applicantCol,
    ...(sort === "best" ? [fitCol] : []),
    statusCol,
    revealCol,
    appliedCol,
    actionsCol,
  ];

  const reasonValid = reason.trim().length >= MIN_REASON;

  const rankPermissionError =
    rankingQuery.isError &&
    rankingQuery.error instanceof ApiError &&
    rankingQuery.error.isPermissionError;

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
          {/* Stage filter chips + Newest / Best-match sort */}
          <div className="mb-4 space-y-2">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div
                className="flex flex-wrap gap-2"
                role="group"
                aria-label={t("filterStatusLabel")}
              >
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
              <SegmentedControl
                size="sm"
                ariaLabel={t("sortLabel")}
                value={sort}
                onValueChange={(v) => setSort(v as SortMode)}
                options={[
                  { value: "newest", label: t("sortNewest") },
                  { value: "best", label: t("sortBestMatch") },
                ]}
              />
            </div>
            {!query.isPending && rows.length > 0 && (
              <p className="text-xs font-medium tabular-nums text-[var(--text-muted)]">
                {t("resultCount", { count: filteredRows.length })}
              </p>
            )}
          </div>

          {/* Best-match advisory / honest signal states */}
          {sort === "best" && (
            <>
              {rankingQuery.isError ? (
                <div className="mb-4 flex items-center justify-between gap-3 rounded-xl border border-[var(--border-default)] bg-white px-3.5 py-2.5">
                  <p className="flex items-start gap-2 text-xs text-[var(--text-secondary)]">
                    {rankPermissionError ? (
                      <ShieldWarning
                        aria-hidden
                        weight="duotone"
                        className="mt-0.5 size-4 shrink-0 text-[var(--text-muted)]"
                      />
                    ) : (
                      <WarningCircle
                        aria-hidden
                        weight="duotone"
                        className="mt-0.5 size-4 shrink-0 text-[var(--brand-red)]"
                      />
                    )}
                    {rankPermissionError
                      ? t("fitRankPermission")
                      : t("fitRankError")}
                  </p>
                  {!rankPermissionError && (
                    <Button
                      variant="secondary"
                      size="sm"
                      onClick={() => rankingQuery.refetch()}
                    >
                      {tc("retry")}
                    </Button>
                  )}
                </div>
              ) : rankingSignal === "no_requirements" ? (
                <div className="mb-4 flex items-start gap-2 rounded-xl border border-[var(--amber-600)]/40 bg-[var(--amber-100)] px-3.5 py-2.5">
                  <WarningCircle
                    aria-hidden
                    weight="duotone"
                    className="mt-0.5 size-4 shrink-0 text-[var(--amber-700)]"
                  />
                  <p className="text-xs text-[var(--amber-700)]">
                    {t("fitNoRequirements")}
                  </p>
                </div>
              ) : (
                <div className="mb-4 flex items-start gap-2 rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-subtle)]/50 px-3.5 py-2.5">
                  <Sparkle
                    aria-hidden
                    weight="duotone"
                    className="mt-0.5 size-4 shrink-0 text-[var(--text-muted)]"
                  />
                  <p className="text-xs text-[var(--text-secondary)]">
                    <span className="font-semibold text-[var(--text-primary)]">
                      {t("fitTitle")}
                    </span>
                    {" — "}
                    {t("fitAdvisory")}
                    {rankingSignal === "low_signal" && ` ${t("fitLowSignal")}`}
                  </p>
                </div>
              )}
            </>
          )}

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
              rows={displayedRows}
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

      {/* Candidate detail drawer — wide, two-column (review + embedded CV) */}
      <Sheet
        open={!!selectedId}
        onClose={() => setSelectedId(null)}
        title={t("detailTitle")}
        closeLabel={tc("close")}
        size="wide"
      >
        {selectedId && (
          <div className="flex min-h-full flex-col">
            {/* Prev / Next pager — stays mounted across paging so focus is kept */}
            <div className="mb-4 flex items-center justify-between gap-2 border-b border-white/40 pb-3">
              <div className="flex items-center gap-1.5">
                <Button
                  ref={prevBtnRef}
                  variant="secondary"
                  size="sm"
                  disabled={!hasPrev}
                  onClick={() => goTo("prev")}
                  aria-label={t("prevCandidate")}
                >
                  <CaretLeft aria-hidden weight="bold" className="size-4" />
                  <span className="hidden sm:inline">{t("prev")}</span>
                </Button>
                <Button
                  ref={nextBtnRef}
                  variant="secondary"
                  size="sm"
                  disabled={!hasNext}
                  onClick={() => goTo("next")}
                  aria-label={t("nextCandidate")}
                >
                  <span className="hidden sm:inline">{t("next")}</span>
                  <CaretRight aria-hidden weight="bold" className="size-4" />
                </Button>
              </div>
              {selectedIndex >= 0 && (
                <span
                  aria-live="polite"
                  className="text-xs font-medium tabular-nums text-[var(--text-muted)]"
                >
                  {t("candidatePosition", {
                    index: selectedIndex + 1,
                    total: orderedForNav.length,
                  })}
                </span>
              )}
            </div>

            <div className="flex-1">
              {detailQuery.isPending ? (
                <p className="text-sm text-[var(--text-muted)]">{tc("loading")}</p>
              ) : detailQuery.isError || !selected ? (
                <EmptyState
                  kind="error"
                  icon={WarningCircle}
                  title={tStates("errorTitle")}
                  description={tStates("errorBody")}
                  action={
                    <Button
                      variant="secondary"
                      onClick={() => detailQuery.refetch()}
                    >
                      {tc("retry")}
                    </Button>
                  }
                />
              ) : (
                <CandidateDetail
                  app={selected}
                  jobTitle={jobTitle}
                  fit={fitByAppId.get(selected.id) ?? null}
                  downloading={downloading}
                  reviewPending={
                    reviewMutation.isPending &&
                    reviewMutation.variables === selected.id
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
            </div>
          </div>
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
