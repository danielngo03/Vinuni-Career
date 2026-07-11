"use client";

import * as React from "react";
import { useLocale, useTranslations } from "next-intl";
import {
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import {
  CircleDollarSign,
  FileEdit,
  Hourglass,
  Megaphone,
  Pause,
  Play,
  Plus,
  Send,
  Square,
  Target,
  Trash2,
} from "lucide-react";
import { Button, Modal, SponsoredLabel, useToast } from "@/components/ui";
import {
  DataTable,
  DetailRow,
  DetailSheet,
  DetailSheetSection,
  EmptyState,
  GradientHeroCard,
  KpiRow,
  KpiTile,
  PageHeader,
  StatusChip,
  type ColumnDef,
} from "@/components/kit";
import { cn } from "@/lib/utils";
import { CampaignBuilderModal } from "./campaign-builder-modal";
import {
  CAMPAIGN_OBJECTIVE_TONE,
  CAMPAIGN_STATUS_TONE,
  useCampaignLabels,
} from "@/lib/advertising/campaign-labels";
import { useReachSummary } from "@/lib/advertising/use-reach-summary";
import { daysUntil, formatVnd, formatWindow } from "@/lib/advertising/format";
import { useApiErrorMessage } from "@/lib/auth/use-api-error";
import {
  ApiError,
  advertisingApi,
  CAMPAIGN_STATUSES,
  type AdCampaign,
  type CampaignPerformance,
} from "@/lib/api";

const nf = new Intl.NumberFormat();

const EDITABLE = new Set<string>(["draft", "rejected"]);
const DELETABLE = new Set<string>(["draft", "rejected"]);
const SUBMITTABLE = new Set<string>(["draft", "rejected"]);

export function CampaignManagerScreen() {
  const t = useTranslations("advertising.campaign");
  const ta = useTranslations("advertising");
  const tStates = useTranslations("states");
  const tc = useTranslations("common");
  const locale = useLocale();
  const labels = useCampaignLabels();
  const toast = useToast();
  const qc = useQueryClient();
  const getMessage = useApiErrorMessage();

  const [statusFilter, setStatusFilter] = React.useState<string>("all");
  const [formOpen, setFormOpen] = React.useState(false);
  const [editing, setEditing] = React.useState<AdCampaign | null>(null);
  const [detailId, setDetailId] = React.useState<string | null>(null);
  const [endTarget, setEndTarget] = React.useState<AdCampaign | null>(null);
  const [deleteTarget, setDeleteTarget] = React.useState<AdCampaign | null>(null);

  const query = useInfiniteQuery({
    queryKey: ["advertising", "campaigns", statusFilter],
    queryFn: ({ pageParam }) =>
      advertisingApi.listCampaigns({
        cursor: pageParam,
        limit: 20,
        status: statusFilter === "all" ? undefined : statusFilter,
      }),
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.page.next_cursor,
    retry: false,
  });

  const rows: AdCampaign[] = React.useMemo(
    () => query.data?.pages.flatMap((p) => p.data) ?? [],
    [query.data],
  );

  const detail = detailId ? (rows.find((r) => r.id === detailId) ?? null) : null;

  /* Honest roll-up computed from the loaded rows (never fabricated). */
  const rollup = React.useMemo(() => {
    let active = 0;
    let pending = 0;
    let drafts = 0;
    let activeBudget = 0;
    for (const c of rows) {
      if (c.status === "active") {
        active += 1;
        activeBudget += Number(c.budget_amount ?? 0);
      } else if (c.status === "pending_review") pending += 1;
      else if (c.status === "draft") drafts += 1;
    }
    return { active, pending, drafts, activeBudget };
  }, [rows]);

  function refresh() {
    void qc.invalidateQueries({ queryKey: ["advertising", "campaigns"] });
  }

  function handleMutationError(e: unknown) {
    if (e instanceof ApiError && e.isConflict) {
      toast.show({ tone: "error", title: t("errors.conflictTitle"), description: t("errors.conflictBody") });
      refresh();
      return;
    }
    toast.show({ tone: "error", title: getMessage(e) });
  }

  const submit = useMutation({
    mutationFn: (c: AdCampaign) =>
      advertisingApi.submitCampaign(c.id, { disclosure_confirmed: c.disclosure_confirmed, version: c.version }),
    onSuccess: () => {
      toast.show({ tone: "success", title: t("toast.submitted") });
      refresh();
    },
    onError: handleMutationError,
  });

  const pause = useMutation({
    mutationFn: (c: AdCampaign) => advertisingApi.pauseCampaign(c.id, c.version),
    onSuccess: () => {
      toast.show({ tone: "success", title: t("toast.paused") });
      refresh();
    },
    onError: handleMutationError,
  });

  const resume = useMutation({
    mutationFn: (c: AdCampaign) => advertisingApi.resumeCampaign(c.id, c.version),
    onSuccess: () => {
      toast.show({ tone: "success", title: t("toast.resumed") });
      refresh();
    },
    onError: handleMutationError,
  });

  const end = useMutation({
    mutationFn: (c: AdCampaign) => advertisingApi.endCampaign(c.id, c.version),
    onSuccess: () => {
      setEndTarget(null);
      setDetailId(null);
      toast.show({ tone: "success", title: t("toast.ended") });
      refresh();
    },
    onError: (e) => {
      setEndTarget(null);
      handleMutationError(e);
    },
  });

  const remove = useMutation({
    mutationFn: (c: AdCampaign) => advertisingApi.deleteCampaign(c.id),
    onSuccess: () => {
      setDeleteTarget(null);
      setDetailId(null);
      toast.show({ tone: "success", title: t("toast.deleted") });
      refresh();
    },
    onError: (e) => {
      setDeleteTarget(null);
      handleMutationError(e);
    },
  });

  const newButton = (
    <Button
      variant="primary"
      size="sm"
      onClick={() => {
        setEditing(null);
        setFormOpen(true);
      }}
    >
      <Plus className="size-4" strokeWidth={2} />
      {t("new")}
    </Button>
  );

  const header = <PageHeader title={t("title")} description={t("subtitle")} actions={newButton} />;

  /* Permission / auth state. */
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

  const columns: ColumnDef<AdCampaign, unknown>[] = [
    {
      id: "campaign",
      header: t("col.campaign"),
      cell: ({ row }) => {
        const c = row.original;
        const serving = c.status === "active" && c.delivery?.serving_eligible;
        return (
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <span className="truncate font-semibold text-foreground">{c.name}</span>
              {serving && <SponsoredLabel label={ta("sponsoredTag")} />}
            </div>
            <div className="mt-1 flex flex-wrap items-center gap-1.5">
              <StatusChip tone={CAMPAIGN_OBJECTIVE_TONE[c.objective] ?? "neutral"} size="sm">
                {labels.objective(c.objective, c.objective_label)}
              </StatusChip>
              <span className="type-caption text-muted-foreground">{labels.surface(c.surface)}</span>
            </div>
          </div>
        );
      },
    },
    {
      accessorKey: "status",
      header: t("col.status"),
      cell: ({ row }) => {
        const c = row.original;
        const noCreative = !c.creative?.headline && !c.creative?.image_ref;
        return (
          <div className="flex flex-col items-start gap-1">
            <StatusChip tone={CAMPAIGN_STATUS_TONE[c.status] ?? "neutral"} dot>
              {labels.status(c.status, c.status_label)}
            </StatusChip>
            {c.status === "rejected" && (
              <span className="type-caption font-medium" style={{ color: "var(--content-danger)" }}>
                {t("reviewNeeded")}
              </span>
            )}
            {c.status !== "ended" && c.status !== "rejected" && noCreative && (
              <span className="type-caption font-medium" style={{ color: "var(--content-warning)" }}>
                {t("detail.noCreative")}
              </span>
            )}
          </div>
        );
      },
    },
    {
      id: "budget",
      header: t("col.budget"),
      meta: { align: "right" },
      cell: ({ row }) => <BudgetCell campaign={row.original} locale={locale} labels={labels} />,
    },
    {
      id: "schedule",
      header: t("col.schedule"),
      cell: ({ row }) => {
        const c = row.original;
        const days = c.status === "active" ? daysUntil(c.end_at) : null;
        return (
          <div className="text-muted-foreground">
            <span className="type-caption">{formatWindow(c.start_at, c.end_at, locale)}</span>
            {days != null && days >= 0 && (
              <span
                className="mt-0.5 block type-caption font-semibold"
                style={{ color: days <= 1 ? "var(--content-danger)" : "var(--content-success)" }}
              >
                {days <= 1 ? t("endingSoon") : t("daysLeft", { count: days })}
              </span>
            )}
          </div>
        );
      },
    },
    {
      id: "delivery",
      header: t("col.delivery"),
      meta: { align: "right" },
      cell: ({ row }) => {
        const c = row.original;
        const d = c.delivery;
        if (c.status !== "active" || !d) {
          return <span className="type-caption text-muted-foreground">{t("notStarted")}</span>;
        }
        const tone = d.budget_exhausted
          ? "var(--content-danger)"
          : d.paced_out
            ? "var(--content-warning)"
            : "var(--content-success)";
        const label = d.budget_exhausted ? t("budgetExhausted") : d.paced_out ? t("pacedOut") : t("servingNow");
        return (
          <div className="text-right">
            <span className="type-caption font-semibold" style={{ color: tone }}>
              {label}
            </span>
            <div className="type-caption text-muted-foreground">
              {nf.format(d.impressions_today)} {t("impressionsShort")}
            </div>
          </div>
        );
      },
    },
  ];

  return (
    <>
      {header}

      {/* Blue hero — active budget/spend (honest, computed from loaded rows). */}
      <GradientHeroCard
        className="mb-4"
        icon={CircleDollarSign}
        eyebrow={t("heroEyebrow")}
        title={t("heroTitle")}
        value={formatVnd(String(rollup.activeBudget), "VND", locale)}
        caption={t("heroCaption", { active: rollup.active, pending: rollup.pending })}
      />

      <KpiRow cols={3} className="mb-4">
        <KpiTile label={t("kpi.active")} value={nf.format(rollup.active)} icon={Megaphone} />
        <KpiTile label={t("kpi.pendingReview")} value={nf.format(rollup.pending)} icon={Hourglass} />
        <KpiTile label={t("kpi.drafts")} value={nf.format(rollup.drafts)} icon={FileEdit} />
      </KpiRow>

      {/* Non-removable disclosure notice */}
      <div
        className="mb-4 flex items-start gap-2.5 rounded-xl border border-border px-3.5 py-3"
        style={{ background: "var(--content-warning-soft)" }}
      >
        <Megaphone className="mt-0.5 size-4 shrink-0" strokeWidth={1.9} style={{ color: "var(--content-warning)" }} />
        <p className="type-small text-foreground">{t("disclosureNotice")}</p>
      </div>

      {/* Status filter chips */}
      <div className="mb-4 flex flex-wrap gap-1.5" role="group" aria-label={t("filterLabel")}>
        {(["all", ...CAMPAIGN_STATUSES] as const).map((s) => (
          <button
            key={s}
            onClick={() => setStatusFilter(s)}
            aria-pressed={statusFilter === s}
            className={cn(
              "inline-flex items-center rounded-full border px-3 py-1 text-[0.8125rem] font-medium outline-none transition-colors focus-visible:ring-2 focus-visible:ring-[var(--field-focus-border)]",
              statusFilter === s
                ? "border-transparent bg-foreground text-[var(--surface-card)]"
                : "border-border bg-card text-muted-foreground hover:text-foreground",
            )}
          >
            {s === "all" ? t("allStatuses") : labels.status(s)}
          </button>
        ))}
      </div>

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
            loading={query.isPending}
            onRowClick={(r) => setDetailId(r.id)}
            activeRowId={detailId ?? undefined}
            empty={
              <EmptyState
                kind="empty"
                icon={Megaphone}
                title={statusFilter === "all" ? t("empty.allTitle") : t("empty.filterTitle")}
                description={statusFilter === "all" ? t("empty.allBody") : t("empty.filterBody")}
                action={statusFilter === "all" ? newButton : undefined}
              />
            }
          />
          {query.hasNextPage && (
            <div className="mt-4 flex justify-center">
              <Button variant="secondary" loading={query.isFetchingNextPage} onClick={() => query.fetchNextPage()}>
                {tc("loadMore")}
              </Button>
            </div>
          )}
        </>
      )}

      {/* Detail drawer */}
      <CampaignDetailSheet
        campaign={detail}
        onClose={() => setDetailId(null)}
        onEdit={(c) => {
          setDetailId(null);
          setEditing(c);
          setFormOpen(true);
        }}
        onSubmit={(c) => submit.mutate(c)}
        onPause={(c) => pause.mutate(c)}
        onResume={(c) => resume.mutate(c)}
        onEnd={(c) => setEndTarget(c)}
        onDelete={(c) => setDeleteTarget(c)}
        busy={submit.isPending || pause.isPending || resume.isPending}
      />

      {/* Builder */}
      <CampaignBuilderModal open={formOpen} onClose={() => setFormOpen(false)} campaign={editing} />

      {/* End confirm */}
      <Modal
        open={endTarget !== null}
        onClose={() => setEndTarget(null)}
        title={t("confirm.endTitle")}
        description={t("confirm.endBody", { name: endTarget?.name ?? "" })}
        size="sm"
        closeLabel={tc("close")}
        footer={
          <>
            <Button variant="ghost" onClick={() => setEndTarget(null)}>
              {tc("back")}
            </Button>
            <Button variant="danger" loading={end.isPending} onClick={() => endTarget && end.mutate(endTarget)}>
              {t("confirm.endConfirm")}
            </Button>
          </>
        }
      >
        <p className="type-small text-muted-foreground">{t("confirm.endBody", { name: endTarget?.name ?? "" })}</p>
      </Modal>

      {/* Delete confirm */}
      <Modal
        open={deleteTarget !== null}
        onClose={() => setDeleteTarget(null)}
        title={t("confirm.deleteTitle")}
        description={t("confirm.deleteBody", { name: deleteTarget?.name ?? "" })}
        size="sm"
        closeLabel={tc("close")}
        footer={
          <>
            <Button variant="ghost" onClick={() => setDeleteTarget(null)}>
              {tc("back")}
            </Button>
            <Button variant="danger" loading={remove.isPending} onClick={() => deleteTarget && remove.mutate(deleteTarget)}>
              {t("confirm.deleteConfirm")}
            </Button>
          </>
        }
      >
        <p className="type-small text-muted-foreground">{t("confirm.deleteBody", { name: deleteTarget?.name ?? "" })}</p>
      </Modal>
    </>
  );
}

/* -------------------------------------------------------------------------- */
/* Budget cell (spent / budget + mini progress)                                */
/* -------------------------------------------------------------------------- */

function BudgetCell({
  campaign,
  locale,
  labels,
}: {
  campaign: AdCampaign;
  locale: string;
  labels: ReturnType<typeof useCampaignLabels>;
}) {
  const t = useTranslations("advertising.campaign");
  const budget = Number(campaign.budget_amount ?? 0);
  const spent = Number(campaign.spent_amount ?? 0);
  const pct = budget > 0 ? Math.min(100, Math.round((spent / budget) * 100)) : 0;
  return (
    <div className="flex flex-col items-end gap-1">
      <span className="font-semibold tabular-nums text-foreground">
        {formatVnd(campaign.budget_amount, campaign.currency, locale)}
      </span>
      <div className="h-1.5 w-24 overflow-hidden rounded-full bg-[var(--bg-subtle)]">
        <div className="h-full rounded-full" style={{ width: `${pct}%`, background: "var(--content-info)" }} />
      </div>
      <span className="type-caption text-muted-foreground">
        {formatVnd(campaign.spent_amount, campaign.currency, locale)} {t("spentLabel")} · {labels.pacing(campaign.pacing)}
      </span>
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* Detail sheet (with live performance fetch)                                  */
/* -------------------------------------------------------------------------- */

function CampaignDetailSheet({
  campaign,
  onClose,
  onEdit,
  onSubmit,
  onPause,
  onResume,
  onEnd,
  onDelete,
  busy,
}: {
  campaign: AdCampaign | null;
  onClose: () => void;
  onEdit: (c: AdCampaign) => void;
  onSubmit: (c: AdCampaign) => void;
  onPause: (c: AdCampaign) => void;
  onResume: (c: AdCampaign) => void;
  onEnd: (c: AdCampaign) => void;
  onDelete: (c: AdCampaign) => void;
  busy: boolean;
}) {
  const t = useTranslations("advertising.campaign");
  const ta = useTranslations("advertising");
  const tc = useTranslations("common");
  const locale = useLocale();
  const labels = useCampaignLabels();
  const reachSummary = useReachSummary();

  const perfQuery = useQuery({
    queryKey: ["advertising", "campaign-performance", campaign?.id],
    queryFn: () => advertisingApi.campaignPerformance(campaign!.id),
    enabled: !!campaign,
    staleTime: 60 * 1000,
    retry: false,
  });

  if (!campaign) return null;
  const c = campaign;
  const perf: CampaignPerformance | null = perfQuery.data ?? null;
  const hasPerf = perf && perf.impressions > 0;
  const serving = c.status === "active" && c.delivery?.serving_eligible;
  const noCreative = !c.creative?.headline && !c.creative?.image_ref;

  const metricTiles = [
    { key: "impressions", label: t("detail.impressions"), value: nf.format(perf?.impressions ?? 0) },
    { key: "clicks", label: t("detail.clicks"), value: nf.format(perf?.clicks ?? 0) },
    { key: "ctr", label: t("detail.ctr"), value: perf ? `${(perf.ctr * 100).toFixed(1)}%` : "—" },
    { key: "applyStarts", label: t("detail.applyStarts"), value: nf.format(perf?.apply_starts ?? 0) },
  ];

  return (
    <DetailSheet
      open={!!campaign}
      onClose={onClose}
      title={c.name}
      subtitle={labels.surface(c.surface)}
      width="lg"
      closeLabel={tc("close")}
      status={
        <>
          <StatusChip tone={CAMPAIGN_STATUS_TONE[c.status] ?? "neutral"} dot>
            {labels.status(c.status, c.status_label)}
          </StatusChip>
          <StatusChip tone={CAMPAIGN_OBJECTIVE_TONE[c.objective] ?? "neutral"} size="sm">
            {labels.objective(c.objective, c.objective_label)}
          </StatusChip>
          {serving && <SponsoredLabel label={ta("sponsoredTag")} />}
        </>
      }
      footer={
        <>
          {SUBMITTABLE.has(c.status) && (
            <Button variant="primary" size="sm" disabled={busy || !c.disclosure_confirmed} onClick={() => onSubmit(c)}>
              <Send className="size-4" strokeWidth={1.8} />
              {t("action.submit")}
            </Button>
          )}
          {EDITABLE.has(c.status) && (
            <Button variant="secondary" size="sm" onClick={() => onEdit(c)}>
              <FileEdit className="size-4" strokeWidth={1.8} />
              {c.status === "rejected" ? t("action.editResubmit") : t("action.edit")}
            </Button>
          )}
          {c.status === "active" && (
            <Button variant="secondary" size="sm" disabled={busy} onClick={() => onPause(c)}>
              <Pause className="size-4" strokeWidth={1.8} />
              {t("action.pause")}
            </Button>
          )}
          {c.status === "paused" && (
            <Button variant="secondary" size="sm" disabled={busy} onClick={() => onResume(c)}>
              <Play className="size-4" strokeWidth={1.8} />
              {t("action.resume")}
            </Button>
          )}
          {(c.status === "approved" || c.status === "active" || c.status === "paused") && (
            <Button variant="ghost" size="sm" onClick={() => onEnd(c)}>
              <Square className="size-4" strokeWidth={1.8} />
              {t("action.end")}
            </Button>
          )}
          {DELETABLE.has(c.status) && (
            <Button variant="danger" size="sm" onClick={() => onDelete(c)}>
              <Trash2 className="size-4" strokeWidth={1.8} />
              {t("action.delete")}
            </Button>
          )}
        </>
      }
    >
      {c.status === "rejected" && c.moderation_note && (
        <div
          className="mb-3 rounded-lg px-3 py-2 type-small"
          style={{ background: "var(--content-danger-soft)", color: "var(--content-danger)" }}
          role="alert"
        >
          {t("detail.rejectReason", { reason: c.moderation_note })}
        </div>
      )}

      <DetailSheetSection title={t("detail.budgetSection")}>
        <dl>
          <DetailRow label={t("detail.budget")}>
            <span className="tabular-nums">{formatVnd(c.budget_amount, c.currency, locale)}</span>
          </DetailRow>
          <DetailRow label={t("detail.spent")}>
            <span className="tabular-nums">{formatVnd(c.spent_amount, c.currency, locale)}</span>
          </DetailRow>
          <DetailRow label={t("detail.pacing")}>{labels.pacing(c.pacing, c.pacing_label)}</DetailRow>
          <DetailRow label={t("detail.schedule")}>{formatWindow(c.start_at, c.end_at, locale)}</DetailRow>
          {c.delivery && (
            <>
              <DetailRow label={t("detail.impressionGoal")}>
                <span className="tabular-nums">{nf.format(c.delivery.impression_goal)}</span>
              </DetailRow>
              <DetailRow label={t("detail.servingState")}>
                <StatusChip tone={c.delivery.serving_eligible ? "success" : "neutral"} size="sm">
                  {c.delivery.serving_eligible ? t("detail.eligible") : t("detail.notEligible")}
                </StatusChip>
              </DetailRow>
            </>
          )}
        </dl>
      </DetailSheetSection>

      <DetailSheetSection title={t("detail.targetingSection")}>
        <p className="flex items-start gap-2 type-small text-foreground">
          <Target aria-hidden className="mt-0.5 size-4 shrink-0 text-muted-foreground" strokeWidth={1.8} />
          {reachSummary(c.targeting)}
        </p>
      </DetailSheetSection>

      <DetailSheetSection title={t("detail.creativeSection")}>
        {noCreative ? (
          <p className="type-small" style={{ color: "var(--content-warning)" }}>
            {t("detail.noCreative")}
          </p>
        ) : (
          <div className="rounded-lg border border-border bg-[var(--bg-subtle)] p-3">
            {c.creative?.headline && <p className="font-semibold text-foreground">{c.creative.headline}</p>}
            {c.creative?.body && <p className="mt-1 type-small text-muted-foreground">{c.creative.body}</p>}
            <div className="mt-2">
              <SponsoredLabel label={c.disclosure?.label ?? ta("sponsoredTag")} />
            </div>
          </div>
        )}
        <p className="mt-2 type-caption text-muted-foreground">
          {t("detail.disclosureLine", { label: c.disclosure?.label ?? ta("sponsoredTag") })}
        </p>
      </DetailSheetSection>

      <DetailSheetSection title={t("detail.performanceSection")}>
        {perfQuery.isError ? (
          <EmptyState kind="error" title={t("detail.noPerformance")} description={t("detail.noPerformanceBody")} />
        ) : !hasPerf ? (
          <EmptyState kind="empty" title={t("detail.noPerformance")} description={t("detail.noPerformanceBody")} />
        ) : (
          <dl className="grid grid-cols-2 gap-2.5">
            {metricTiles.map((m) => (
              <div key={m.key} className="rounded-lg border border-border bg-[var(--bg-subtle)] px-3 py-2">
                <dt className="type-caption text-muted-foreground">{m.label}</dt>
                <dd className="mt-0.5 text-base font-bold tabular-nums text-foreground">{m.value}</dd>
              </div>
            ))}
          </dl>
        )}
      </DetailSheetSection>
    </DetailSheet>
  );
}
