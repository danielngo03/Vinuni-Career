"use client";

import * as React from "react";
import { useSearchParams } from "next/navigation";
import { useTranslations } from "next-intl";
import {
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import {
  ArrowLeft,
  ArrowUpDown,
  BadgeCheck,
  Ban,
  CheckCheck,
  ChevronLeft,
  ChevronRight,
  Copy,
  Download,
  Eye,
  Inbox,
  Kanban,
  Loader2,
  LogIn,
  MoreHorizontal,
  Search,
  ShieldAlert,
  UserRound,
  Users2,
} from "lucide-react";
import { Link } from "@/i18n/navigation";
import { Button, useToast } from "@/components/ui";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
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
import { formatDateShort, formatDateTimeShort } from "@/lib/format";
import { useApplicationLabels } from "@/lib/applications/labels";
import {
  ApiError,
  applicationsApi,
  jobsApi,
  organizationApi,
  resolveDownloadUrl,
  type PartnerApplication,
  type RejectionReason,
} from "@/lib/api";
import { useApiErrorMessage } from "@/lib/auth/use-api-error";
import { CandidateDetail } from "./candidates-screen/candidate-detail";
import { RejectModal } from "./candidates-screen/reject-modal";
import { MatchRing, matchTierKey, matchTone } from "./candidates-screen/match-ring";
import {
  nowIso,
  sortRows,
  SORT_KEYS,
  STAGE_FILTERS,
  type ForJobData,
  type SortKey,
} from "./candidates-screen/utils";
import { APPLICATION_STATUS_CHIP, initials } from "./chip-tones";

const nf = new Intl.NumberFormat();

type RejectTarget =
  | { kind: "single"; id: string }
  | { kind: "bulk"; ids: string[]; clear: () => void };

/** Assignee filter value: "all" | "mine" | "unassigned" | a membership id. */
type AssigneeFilter = string;

export function PartnerCandidatesScreen({ jobId }: { jobId: string }) {
  const t = useTranslations("candidates");
  const tStates = useTranslations("states");
  const tc = useTranslations("common");
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
  const [sortKey, setSortKey] = React.useState<SortKey>("needs_action");
  const [assigneeFilter, setAssigneeFilter] = React.useState<AssigneeFilter>("all");
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

  // Team directory + "me" — drive the assignee filter (read-only; there is no
  // application-assign endpoint yet, see handoff).
  const capsQuery = useQuery({
    queryKey: ["org", "me", "capabilities"],
    queryFn: () => organizationApi.getMyCapabilities(),
    retry: false,
    staleTime: 5 * 60_000,
  });
  const membersQuery = useQuery({
    queryKey: ["org", "members"],
    queryFn: () => organizationApi.listMembers(),
    retry: false,
    staleTime: 5 * 60_000,
  });
  const myMembershipId = capsQuery.data?.membership_id ?? null;
  const members = React.useMemo(
    () =>
      (membersQuery.data?.data ?? [])
        .filter((m) => m.status === "active")
        .map((m) => ({ id: m.id, name: m.full_name || m.user_email })),
    [membersQuery.data],
  );

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

  // Parent owns filter + sort so the table order === prev/next order === count.
  const visibleRows: PartnerApplication[] = React.useMemo(() => {
    let out = rows;
    if (statusFilter !== "all") out = out.filter((r) => r.status === statusFilter);
    if (assigneeFilter === "unassigned") {
      out = out.filter((r) => !r.assignee);
    } else if (assigneeFilter === "mine") {
      out = out.filter((r) => r.assignee?.membership_id === myMembershipId);
    } else if (assigneeFilter !== "all") {
      out = out.filter((r) => r.assignee?.membership_id === assigneeFilter);
    }
    const q = search.trim().toLowerCase();
    if (q) {
      out = out.filter(
        (r) =>
          r.applicant.full_name.toLowerCase().includes(q) ||
          (r.applicant.email?.toLowerCase().includes(q) ?? false) ||
          (r.applicant.headline?.toLowerCase().includes(q) ?? false),
      );
    }
    return sortRows(out, sortKey);
  }, [rows, statusFilter, assigneeFilter, myMembershipId, search, sortKey]);

  const detailQuery = useQuery({
    queryKey: ["applications", "partnerDetail", selectedId],
    queryFn: () => applicationsApi.getForPartner(selectedId as string),
    enabled: !!selectedId,
    retry: false,
  });

  const selected = detailQuery.data;
  const detailKey = (id: string) =>
    ["applications", "partnerDetail", id] as const;

  /* --------- prev/next: STABLE ordered snapshot captured on drawer open ------ */
  const [navOrder, setNavOrder] = React.useState<string[]>([]);
  const drawerOpenRef = React.useRef(false);
  React.useEffect(() => {
    if (!selectedId) {
      drawerOpenRef.current = false;
      if (navOrder.length) setNavOrder([]);
      return;
    }
    // Snapshot once per open session, as soon as rows are available, so a status
    // mutation that re-sorts/re-filters the live list can't make prev/next jump.
    if (!drawerOpenRef.current && visibleRows.length > 0) {
      setNavOrder(visibleRows.map((r) => r.id));
      drawerOpenRef.current = true;
    }
  }, [selectedId, visibleRows, navOrder.length]);

  const navIds = navOrder.length ? navOrder : visibleRows.map((r) => r.id);
  const currentIndex = selectedId ? navIds.indexOf(selectedId) : -1;
  const prevId = currentIndex > 0 ? navIds[currentIndex - 1]! : null;
  const nextId =
    currentIndex >= 0 && currentIndex < navIds.length - 1
      ? navIds[currentIndex + 1]!
      : null;

  // ←/→ keyboard navigation while the drawer is open (ignores form fields).
  React.useEffect(() => {
    if (!selectedId || rejectTarget) return;
    const onKey = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement | null;
      if (el && /^(INPUT|TEXTAREA|SELECT)$/.test(el.tagName)) return;
      if (el?.isContentEditable) return;
      if (e.key === "ArrowLeft" && prevId) {
        e.preventDefault();
        setSelectedId(prevId);
      } else if (e.key === "ArrowRight" && nextId) {
        e.preventDefault();
        setSelectedId(nextId);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [selectedId, prevId, nextId, rejectTarget]);

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

  async function copyEmail(email: string) {
    try {
      await navigator.clipboard.writeText(email);
      toast.show({ tone: "success", title: t("emailCopied") });
    } catch {
      toast.show({ tone: "error", title: t("emailCopyFailed") });
    }
  }

  function handleDownload() {
    const cv = selected?.cv;
    if (!cv) return;
    setDownloading(true);
    try {
      window.open(resolveDownloadUrl(cv.download_url), "_blank", "noopener");
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

  const sortLabel: Record<SortKey, string> = {
    needs_action: t("sortNeedsAction"),
    newest: t("sortNewest"),
    oldest: t("sortOldest"),
    best_match: t("sortBestMatch"),
    status: t("sortStatus"),
  };
  const assigneeLabel =
    assigneeFilter === "all"
      ? t("assigneeAll")
      : assigneeFilter === "mine"
        ? t("assigneeMine")
        : assigneeFilter === "unassigned"
          ? t("unassigned")
          : members.find((m) => m.id === assigneeFilter)?.name ?? t("assigneeAll");

  const columns: ColumnDef<PartnerApplication, unknown>[] = [
    {
      id: "match",
      enableSorting: false,
      header: t("colMatch"),
      size: 72,
      cell: ({ row }) => {
        const score = row.original.fit?.score ?? null;
        return (
          <span title={t("matchTooltip")}>
            <MatchRing
              score={score}
              size={34}
              ariaLabel={score != null ? t("matchAria", { score: Math.round(score) }) : undefined}
            />
          </span>
        );
      },
    },
    {
      id: "applicant",
      enableSorting: false,
      header: t("colApplicant"),
      cell: ({ row }) => {
        const a = row.original.applicant;
        const secondary = a.headline || a.email;
        return (
          <span className="inline-flex min-w-0 items-center gap-2.5">
            <Avatar size="sm">
              {a.avatar_url && <AvatarImage src={a.avatar_url} alt="" />}
              <AvatarFallback>{initials(a.full_name)}</AvatarFallback>
            </Avatar>
            <span className="min-w-0">
              <span className="block truncate font-medium text-foreground">{a.full_name}</span>
              {secondary && (
                <span className="block type-caption truncate text-muted-foreground">{secondary}</span>
              )}
            </span>
          </span>
        );
      },
    },
    {
      id: "status",
      enableSorting: false,
      header: t("colStatus"),
      cell: ({ row }) => (
        <StatusChip tone={APPLICATION_STATUS_CHIP[row.original.status] ?? "neutral"}>
          {labels.status(row.original.status, row.original.status_label)}
        </StatusChip>
      ),
    },
    {
      id: "stage",
      enableSorting: false,
      header: t("colStage"),
      cell: ({ row }) =>
        row.original.stage ? (
          <StatusChip tone="indigo" size="sm">
            {row.original.stage.stage_name}
          </StatusChip>
        ) : (
          <span className="type-caption text-muted-foreground">{t("notInPipeline")}</span>
        ),
    },
    {
      id: "owner",
      enableSorting: false,
      header: t("colOwner"),
      cell: ({ row }) =>
        row.original.assignee ? (
          <span className="type-small truncate text-foreground">
            {row.original.assignee.display_name}
          </span>
        ) : (
          <span className="type-caption text-muted-foreground">{t("unassigned")}</span>
        ),
    },
    {
      id: "applied_at",
      enableSorting: false,
      header: t("colApplied"),
      meta: { align: "right" },
      cell: ({ row }) => (
        <span
          className="type-small tabular-nums text-muted-foreground"
          title={formatDateTimeShort(row.original.applied_at)}
        >
          {formatDateShort(row.original.applied_at)}
        </span>
      ),
    },
    {
      id: "actions",
      enableSorting: false,
      meta: { align: "right" },
      header: "",
      size: 48,
      cell: ({ row }) => {
        const r = row.original;
        const canReview = r.status === "submitted";
        const canReject = r.status === "submitted" || r.status === "under_review";
        return (
          <div className="flex justify-end" onClick={(e) => e.stopPropagation()}>
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <button
                  type="button"
                  aria-label={t("rowActions")}
                  className="inline-flex size-8 items-center justify-center rounded-lg text-muted-foreground outline-none transition-colors hover:bg-[var(--bg-subtle)] hover:text-foreground focus-visible:ring-2 focus-visible:ring-[var(--field-focus-border)]"
                >
                  <MoreHorizontal aria-hidden className="size-4" strokeWidth={1.8} />
                </button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="min-w-[11rem]">
                <DropdownMenuItem onSelect={() => setSelectedId(r.id)}>
                  <Eye aria-hidden strokeWidth={1.8} />
                  {t("openDetail")}
                </DropdownMenuItem>
                {canReview && (
                  <DropdownMenuItem onSelect={() => reviewMutation.mutate(r.id)}>
                    <Search aria-hidden strokeWidth={1.8} />
                    {t("startReview")}
                  </DropdownMenuItem>
                )}
                {r.applicant.email && (
                  <DropdownMenuItem onSelect={() => copyEmail(r.applicant.email as string)}>
                    <Copy aria-hidden strokeWidth={1.8} />
                    {t("copyEmail")}
                  </DropdownMenuItem>
                )}
                {canReject && (
                  <>
                    <DropdownMenuSeparator />
                    <DropdownMenuItem variant="destructive" onSelect={() => openRejectSingle(r.id)}>
                      <Ban aria-hidden strokeWidth={1.8} />
                      {t("reject")}
                    </DropdownMenuItem>
                  </>
                )}
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        );
      },
    },
  ];

  const selApplicant = selected?.applicant;
  const selName = selApplicant?.full_name ?? t("detailTitle");
  const selScore = selected?.fit?.score ?? null;
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
                  {t("resultCount", { count: visibleRows.length })}
                </span>
              ) : undefined
            }
          >
            {/* Sort control — DEFAULT = needs-action (protects review SLA). */}
            <ToolbarMenu icon={ArrowUpDown} label={t("sortLabel")} value={sortLabel[sortKey]}>
              <DropdownMenuLabel>{t("sortLabel")}</DropdownMenuLabel>
              <DropdownMenuRadioGroup
                value={sortKey}
                onValueChange={(v) => setSortKey(v as SortKey)}
              >
                {SORT_KEYS.map((k) => (
                  <DropdownMenuRadioItem key={k} value={k}>
                    {sortLabel[k]}
                  </DropdownMenuRadioItem>
                ))}
              </DropdownMenuRadioGroup>
            </ToolbarMenu>

            {/* Assignee filter — team triage (read-only; no assign endpoint yet). */}
            <ToolbarMenu icon={UserRound} label={t("assigneeLabel")} value={assigneeLabel}>
              <DropdownMenuLabel>{t("assigneeLabel")}</DropdownMenuLabel>
              <DropdownMenuRadioGroup
                value={assigneeFilter}
                onValueChange={setAssigneeFilter}
              >
                <DropdownMenuRadioItem value="all">{t("assigneeAll")}</DropdownMenuRadioItem>
                {myMembershipId && (
                  <DropdownMenuRadioItem value="mine">{t("assigneeMine")}</DropdownMenuRadioItem>
                )}
                <DropdownMenuRadioItem value="unassigned">{t("unassigned")}</DropdownMenuRadioItem>
                {members.length > 0 && <DropdownMenuSeparator />}
                {members.map((m) => (
                  <DropdownMenuRadioItem key={m.id} value={m.id}>
                    {m.name}
                  </DropdownMenuRadioItem>
                ))}
              </DropdownMenuRadioGroup>
            </ToolbarMenu>

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
            data={visibleRows}
            getRowId={(r) => r.id}
            loading={query.isPending}
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
                        setAssigneeFilter("all");
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

      {/* Candidate CV drawer */}
      <DetailSheet
        open={!!selectedId}
        onClose={() => setSelectedId(null)}
        width="lg"
        closeLabel={tc("close")}
        title={selName}
        subtitle={selected ? selected.applicant.headline ?? selected.applicant.email ?? jobTitle : undefined}
        avatar={
          selected ? (
            <Avatar size="lg">
              {selected.applicant.avatar_url && (
                <AvatarImage src={selected.applicant.avatar_url} alt="" />
              )}
              <AvatarFallback>{initials(selName)}</AvatarFallback>
            </Avatar>
          ) : undefined
        }
        status={
          selected ? (
            <>
              {selScore != null && (
                <span className="inline-flex items-center gap-1.5">
                  <MatchRing
                    score={selScore}
                    size={34}
                    ariaLabel={t("matchAria", { score: Math.round(selScore) })}
                  />
                  <StatusChip tone={matchTone(selScore)} size="sm">
                    {t(matchTierKey(selScore))}
                  </StatusChip>
                </span>
              )}
              <StatusChip tone={APPLICATION_STATUS_CHIP[selected.status] ?? "neutral"}>
                {labels.status(selected.status, selected.status_label)}
              </StatusChip>
              {selected.stage && (
                <StatusChip tone="indigo" size="sm">
                  {selected.stage.stage_name}
                </StatusChip>
              )}
            </>
          ) : undefined
        }
        headerActions={
          selected ? (
            <div className="flex items-center gap-1">
              <div
                className="mr-1 flex items-center gap-0.5 rounded-lg border border-border"
                title={t("navKeyHint")}
              >
                <button
                  type="button"
                  aria-label={t("prevCandidate")}
                  aria-keyshortcuts="ArrowLeft"
                  disabled={!prevId}
                  onClick={() => prevId && setSelectedId(prevId)}
                  className="inline-flex size-8 items-center justify-center rounded-l-lg text-muted-foreground outline-none transition-colors hover:bg-[var(--bg-subtle)] hover:text-foreground focus-visible:ring-2 focus-visible:ring-[var(--field-focus-border)] disabled:cursor-not-allowed disabled:opacity-40"
                >
                  <ChevronLeft aria-hidden className="size-4" strokeWidth={1.8} />
                </button>
                {currentIndex >= 0 && (
                  <span className="min-w-[3rem] px-1 text-center type-caption tabular-nums text-muted-foreground">
                    {currentIndex + 1}/{navIds.length}
                  </span>
                )}
                <button
                  type="button"
                  aria-label={t("nextCandidate")}
                  aria-keyshortcuts="ArrowRight"
                  disabled={!nextId}
                  onClick={() => nextId && setSelectedId(nextId)}
                  className="inline-flex size-8 items-center justify-center rounded-r-lg text-muted-foreground outline-none transition-colors hover:bg-[var(--bg-subtle)] hover:text-foreground focus-visible:ring-2 focus-visible:ring-[var(--field-focus-border)] disabled:cursor-not-allowed disabled:opacity-40"
                >
                  <ChevronRight aria-hidden className="size-4" strokeWidth={1.8} />
                </button>
              </div>
              <button
                type="button"
                aria-label={t("downloadCv")}
                disabled={!selected.cv || downloading}
                onClick={handleDownload}
                className="inline-flex size-8 items-center justify-center rounded-lg text-muted-foreground outline-none transition-colors hover:bg-[var(--bg-subtle)] hover:text-foreground focus-visible:ring-2 focus-visible:ring-[var(--field-focus-border)] disabled:cursor-not-allowed disabled:opacity-40"
              >
                <Download aria-hidden className="size-4" strokeWidth={1.8} />
              </button>
              <MessageCandidateButton applicationId={selected.id} />
            </div>
          ) : undefined
        }
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
            <div className="h-[50vh] animate-skeleton rounded-xl bg-[var(--bg-muted)]" />
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
            key={selected.id}
            app={selected}
            downloading={downloading}
            onDownload={handleDownload}
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
    </>
  );
}

/** Toolbar dropdown-select (label + current value) for sort / assignee filters. */
function ToolbarMenu({
  icon: Icon,
  label,
  value,
  children,
}: {
  icon: typeof ArrowUpDown;
  label: string;
  value: string;
  children: React.ReactNode;
}) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          type="button"
          className="inline-flex h-9 items-center gap-1.5 rounded-lg border border-border bg-card px-3 text-[0.8125rem] font-medium text-foreground outline-none transition-colors hover:bg-[var(--bg-subtle)] focus-visible:ring-2 focus-visible:ring-[var(--field-focus-border)]"
        >
          <Icon aria-hidden className="size-4 text-muted-foreground" strokeWidth={1.8} />
          <span className="text-muted-foreground">{label}:</span>
          <span className="max-w-[9rem] truncate">{value}</span>
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="min-w-[12rem]">
        {children}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
