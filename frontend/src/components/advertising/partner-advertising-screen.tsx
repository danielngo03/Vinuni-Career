"use client";

import * as React from "react";
import { useLocale, useTranslations } from "next-intl";
import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Clock,
  ExternalLink,
  Eye,
  Image as ImageIcon,
  Megaphone,
  MousePointerClick,
  Percent,
  Plus,
  Rocket,
  Trash2,
  Wallet,
} from "lucide-react";
import { Link } from "@/i18n/navigation";
import { Button, Modal, SponsoredLabel, useToast } from "@/components/ui";
import {
  DataTable,
  type ColumnDef,
  DetailRow,
  DetailSheet,
  DetailSheetSection,
  EmptyState,
  KpiRow,
  KpiTile,
  PageHeader,
  StatusChip,
  type ChipTone,
} from "@/components/kit";
import { cn } from "@/lib/utils";
import { PlacementFormModal } from "./placement-form-modal";
import { CreativeManagerModal } from "./creative-manager-modal";
import { useAdvertisingLabels } from "@/lib/advertising/labels";
import { daysUntil, formatVnd, formatWindow } from "@/lib/advertising/format";
import { useApiErrorMessage } from "@/lib/auth/use-api-error";
import {
  ApiError,
  advertisingApi,
  dashboardsApi,
  type AdvertisingCampaignRow,
  type Placement,
  type PlacementStatus,
} from "@/lib/api";

const nf = new Intl.NumberFormat();

const STATUS_FILTERS = [
  "all",
  "draft",
  "pending_approval",
  "approved",
  "active",
  "completed",
  "rejected",
  "cancelled",
] as const;

const EDITABLE = new Set<string>(["draft", "rejected"]);
const CANCELLABLE = new Set<string>(["pending_approval", "approved", "active"]);
const MANAGE_CREATIVES = new Set<string>(["draft", "pending_approval", "approved", "active"]);

const STATUS_CHIP_TONE: Record<PlacementStatus, ChipTone> = {
  draft: "neutral",
  pending_approval: "warning",
  approved: "info",
  active: "success",
  completed: "sky",
  rejected: "danger",
  cancelled: "neutral",
};

const TYPE_CHIP_TONE: Record<string, ChipTone> = {
  sponsored: "amber",
  featured: "violet",
  both: "indigo",
};

function spendString(v: string | number | null | undefined): string | null {
  return v == null ? null : String(v);
}

export function PartnerAdvertisingScreen() {
  const t = useTranslations("advertising");
  const tStates = useTranslations("states");
  const tc = useTranslations("common");
  const locale = useLocale();
  const labels = useAdvertisingLabels();
  const toast = useToast();
  const qc = useQueryClient();
  const getMessage = useApiErrorMessage();

  const [statusFilter, setStatusFilter] = React.useState<string>("all");
  const [formOpen, setFormOpen] = React.useState(false);
  const [editing, setEditing] = React.useState<Placement | null>(null);
  const [cancelTarget, setCancelTarget] = React.useState<Placement | null>(null);
  const [deleteTarget, setDeleteTarget] = React.useState<Placement | null>(null);
  const [creativeTargetId, setCreativeTargetId] = React.useState<string | null>(null);
  const [detailId, setDetailId] = React.useState<string | null>(null);

  const query = useInfiniteQuery({
    queryKey: ["advertising", "placements", statusFilter],
    queryFn: ({ pageParam }) =>
      advertisingApi.listPlacements({
        cursor: pageParam,
        limit: 20,
        status: statusFilter === "all" ? undefined : statusFilter,
      }),
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.page.next_cursor,
    retry: false,
  });

  const perfQuery = useQuery({
    queryKey: ["advertising", "performance"],
    queryFn: () => dashboardsApi.partnerAdvertisingPerformance(),
    staleTime: 2 * 60 * 1000,
    retry: false,
  });

  const rows: Placement[] = React.useMemo(
    () => query.data?.pages.flatMap((p) => p.data) ?? [],
    [query.data],
  );

  const perfById = React.useMemo(() => {
    const m = new Map<string, AdvertisingCampaignRow>();
    for (const c of perfQuery.data?.campaigns ?? []) m.set(c.placement_id, c);
    return m;
  }, [perfQuery.data]);

  const totals = perfQuery.data?.totals;

  const inflightTargetIds = React.useMemo(() => {
    const s = new Set<string>();
    for (const p of rows) {
      if (["pending_approval", "approved", "active"].includes(p.status)) s.add(p.target_id);
    }
    return s;
  }, [rows]);

  const creativeTarget = creativeTargetId ? (rows.find((r) => r.id === creativeTargetId) ?? null) : null;
  const detailPlacement = detailId ? (rows.find((r) => r.id === detailId) ?? null) : null;

  function refresh() {
    void qc.invalidateQueries({ queryKey: ["advertising", "placements"] });
    void qc.invalidateQueries({ queryKey: ["advertising", "performance"] });
  }

  function handleMutationError(e: unknown) {
    if (e instanceof ApiError && e.isConflict) {
      toast.show({ tone: "error", title: t("errors.conflictTitle"), description: t("errors.conflictBody") });
      refresh();
      return;
    }
    toast.show({ tone: "error", title: getMessage(e) });
  }

  const cancel = useMutation({
    mutationFn: (p: Placement) => advertisingApi.cancelPlacement(p.id, p.version),
    onSuccess: () => {
      setCancelTarget(null);
      setDetailId(null);
      toast.show({ tone: "success", title: t("toast.cancelled") });
      refresh();
    },
    onError: (e) => {
      setCancelTarget(null);
      handleMutationError(e);
    },
  });

  const remove = useMutation({
    mutationFn: (p: Placement) => advertisingApi.deletePlacement(p.id),
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
      {t("newPlacement")}
    </Button>
  );

  const header = <PageHeader title={t("partnerTitle")} subtitle={t("partnerSubtitle")} actions={newButton} />;

  /* ---- Permission / auth ---- */
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

  const ctr = totals?.ctr_pct;

  const columns: ColumnDef<Placement, unknown>[] = [
    {
      accessorKey: "target_title",
      header: t("colTarget"),
      cell: ({ row }) => {
        const r = row.original;
        const showSponsored = r.status === "active" && (r.placement_type === "sponsored" || r.placement_type === "both");
        return (
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <span className="truncate font-semibold text-foreground">
                {r.target_title ?? t("targetUnavailable")}
              </span>
              {showSponsored && <SponsoredLabel label={t("sponsoredTag")} />}
            </div>
            <span className="type-caption text-muted-foreground">
              {labels.targetType(r.target_type, r.target_type_label)}
            </span>
          </div>
        );
      },
    },
    {
      accessorKey: "placement_type",
      header: t("colType"),
      cell: ({ row }) => (
        <StatusChip tone={TYPE_CHIP_TONE[row.original.placement_type] ?? "neutral"}>
          {labels.placementType(row.original.placement_type, row.original.placement_type_label)}
        </StatusChip>
      ),
    },
    {
      accessorKey: "status",
      header: t("colStatus"),
      cell: ({ row }) => {
        const r = row.original;
        return (
          <div className="flex flex-col items-start gap-1">
            <StatusChip tone={STATUS_CHIP_TONE[r.status] ?? "neutral"} dot>
              {labels.status(r.status, r.status_label)}
            </StatusChip>
            {r.status === "approved" && !r.is_paid && (
              <span className="type-caption font-medium" style={{ color: "var(--content-warning)" }}>
                {t("awaitingPayment")}
              </span>
            )}
            {r.missing_primary_slots && r.missing_primary_slots.length > 0 && (
              <span className="inline-flex items-center gap-1 type-caption font-medium" style={{ color: "var(--content-warning)" }}>
                <ImageIcon className="size-3" strokeWidth={1.9} />
                {t("assetRequired")}
              </span>
            )}
          </div>
        );
      },
    },
    {
      accessorKey: "start_at",
      header: t("colWindow"),
      cell: ({ row }) => {
        const r = row.original;
        const days = r.status === "active" ? daysUntil(r.end_at) : null;
        return (
          <div className="text-muted-foreground">
            <span className="type-caption">{formatWindow(r.start_at, r.end_at, locale)}</span>
            {r.status === "active" && days != null && days >= 0 && (
              <span
                className="mt-0.5 flex items-center gap-1 type-caption font-semibold"
                style={{ color: days <= 1 ? "var(--content-danger)" : "var(--content-success)" }}
              >
                <Clock className="size-3" strokeWidth={1.9} />
                {days <= 1 ? t("endingSoon") : t("daysLeft", { count: days })}
              </span>
            )}
          </div>
        );
      },
    },
    {
      id: "delivery",
      header: t("colDelivery"),
      meta: { align: "right" },
      cell: ({ row }) => {
        const perf = perfById.get(row.original.id);
        if (!perf || perf.impressions === 0) {
          return <span className="type-caption text-muted-foreground">{t("notStarted")}</span>;
        }
        return (
          <div className="text-right">
            <span className="font-semibold tabular-nums text-foreground">{nf.format(perf.impressions)}</span>
            <span className="ml-1 type-caption text-muted-foreground">{t("colImpressions").toLowerCase()}</span>
            <div className="type-caption text-muted-foreground">
              {nf.format(perf.clicks)} {t("colClicks").toLowerCase()}
              {perf.ctr_pct != null && ` · ${perf.ctr_pct}% ${t("colCtr")}`}
            </div>
          </div>
        );
      },
    },
  ];

  return (
    <>
      {header}

      {/* Delivery KPI row — honest zeros/dashes until real ad events arrive */}
      <KpiRow cols={5} className="mb-4">
        <KpiTile label={t("kpi.impressions")} value={nf.format(totals?.impressions ?? 0)} icon={Eye} />
        <KpiTile label={t("kpi.clicks")} value={nf.format(totals?.clicks ?? 0)} icon={MousePointerClick} />
        <KpiTile label={t("kpi.ctr")} value={ctr != null ? `${ctr}%` : "—"} icon={Percent} />
        <KpiTile label={t("kpi.applyStarts")} value={nf.format(totals?.apply_starts ?? 0)} icon={Rocket} />
        <KpiTile
          label={t("kpi.spend")}
          value={formatVnd(spendString(totals?.spend), totals?.currency ?? "VND", locale)}
          icon={Wallet}
        />
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
      <div className="mb-4 flex flex-wrap gap-1.5" role="group" aria-label={t("filterStatusLabel")}>
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
                title={statusFilter === "all" ? t("emptyTitle") : t("emptyFilterTitle")}
                description={statusFilter === "all" ? t("emptyBody") : t("emptyFilterBody")}
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

      {/* Campaign detail drawer */}
      <CampaignDetailSheet
        placement={detailPlacement}
        perf={detailPlacement ? (perfById.get(detailPlacement.id) ?? null) : null}
        onClose={() => setDetailId(null)}
        onEdit={(p) => {
          setDetailId(null);
          setEditing(p);
          setFormOpen(true);
        }}
        onCreatives={(p) => {
          setDetailId(null);
          setCreativeTargetId(p.id);
        }}
        onCancel={(p) => setCancelTarget(p)}
        onDelete={(p) => setDeleteTarget(p)}
      />

      {/* Create / edit */}
      <PlacementFormModal
        open={formOpen}
        onClose={() => setFormOpen(false)}
        placement={editing}
        inflightTargetIds={inflightTargetIds}
      />

      {/* Creatives */}
      <CreativeManagerModal
        open={creativeTarget !== null}
        onClose={() => setCreativeTargetId(null)}
        placement={creativeTarget}
      />

      {/* Cancel */}
      <Modal
        open={cancelTarget !== null}
        onClose={() => setCancelTarget(null)}
        title={t("cancelTitle")}
        description={t("cancelBody", { target: cancelTarget?.target_title ?? "" })}
        size="sm"
        closeLabel={tc("close")}
        footer={
          <>
            <Button variant="ghost" onClick={() => setCancelTarget(null)}>
              {tc("back")}
            </Button>
            <Button variant="danger" loading={cancel.isPending} onClick={() => cancelTarget && cancel.mutate(cancelTarget)}>
              {t("cancelConfirm")}
            </Button>
          </>
        }
      >
        <p className="type-small text-muted-foreground">
          {cancelTarget?.status === "active" ? t("cancelActiveNote") : t("cancelNote")}
        </p>
      </Modal>

      {/* Delete */}
      <Modal
        open={deleteTarget !== null}
        onClose={() => setDeleteTarget(null)}
        title={t("deleteTitle")}
        description={t("deleteBody", { target: deleteTarget?.target_title ?? "" })}
        size="sm"
        closeLabel={tc("close")}
        footer={
          <>
            <Button variant="ghost" onClick={() => setDeleteTarget(null)}>
              {tc("back")}
            </Button>
            <Button variant="danger" loading={remove.isPending} onClick={() => deleteTarget && remove.mutate(deleteTarget)}>
              {tc("delete")}
            </Button>
          </>
        }
      >
        <p className="type-small text-muted-foreground">{t("deleteNote")}</p>
      </Modal>
    </>
  );
}

/* -------------------------------------------------------------------------- */
/* Detail sheet                                                                 */
/* -------------------------------------------------------------------------- */

function CampaignDetailSheet({
  placement,
  perf,
  onClose,
  onEdit,
  onCreatives,
  onCancel,
  onDelete,
}: {
  placement: Placement | null;
  perf: AdvertisingCampaignRow | null;
  onClose: () => void;
  onEdit: (p: Placement) => void;
  onCreatives: (p: Placement) => void;
  onCancel: (p: Placement) => void;
  onDelete: (p: Placement) => void;
}) {
  const t = useTranslations("advertising");
  const tc = useTranslations("common");
  const locale = useLocale();
  const labels = useAdvertisingLabels();

  if (!placement) return null;
  const r = placement;
  const showSponsored = r.status === "active" && (r.placement_type === "sponsored" || r.placement_type === "both");
  const hasDelivery = perf && perf.impressions > 0;

  const metricTiles: { key: string; label: string; value: string }[] = [
    { key: "impressions", label: t("sheet.impressions"), value: nf.format(perf?.impressions ?? 0) },
    { key: "clicks", label: t("sheet.clicks"), value: nf.format(perf?.clicks ?? 0) },
    { key: "ctr", label: t("sheet.ctr"), value: perf?.ctr_pct != null ? `${perf.ctr_pct}%` : "—" },
    { key: "applyStarts", label: t("sheet.applyStarts"), value: nf.format(perf?.apply_starts ?? 0) },
  ];

  return (
    <DetailSheet
      open={!!placement}
      onClose={onClose}
      title={r.target_title ?? t("targetUnavailable")}
      subtitle={labels.targetType(r.target_type, r.target_type_label)}
      closeLabel={tc("close")}
      status={
        <>
          <StatusChip tone={STATUS_CHIP_TONE[r.status] ?? "neutral"} dot>
            {labels.status(r.status, r.status_label)}
          </StatusChip>
          <StatusChip tone={TYPE_CHIP_TONE[r.placement_type] ?? "neutral"}>
            {labels.placementType(r.placement_type, r.placement_type_label)}
          </StatusChip>
          {showSponsored && <SponsoredLabel label={t("sponsoredTag")} />}
        </>
      }
      footer={
        <>
          {MANAGE_CREATIVES.has(r.status) && (
            <Button variant="ghost" size="sm" onClick={() => onCreatives(r)}>
              <ImageIcon className="size-4" strokeWidth={1.8} />
              {t("sheet.creatives")}
            </Button>
          )}
          {EDITABLE.has(r.status) && (
            <Button variant="secondary" size="sm" onClick={() => onEdit(r)}>
              {r.status === "rejected" ? t("editResubmit") : t("editSend")}
            </Button>
          )}
          {EDITABLE.has(r.status) && (
            <Button variant="danger" size="sm" onClick={() => onDelete(r)}>
              <Trash2 className="size-4" strokeWidth={1.8} />
              {tc("delete")}
            </Button>
          )}
          {CANCELLABLE.has(r.status) && (
            <Button variant="danger" size="sm" onClick={() => onCancel(r)}>
              {t("cancelPlacement")}
            </Button>
          )}
        </>
      }
    >
      <DetailSheetSection title={t("sheet.delivery")}>
        {!hasDelivery ? (
          <EmptyState kind="empty" title={t("sheet.noDelivery")} description={t("sheet.noDeliveryBody")} />
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

      <DetailSheetSection title={t("sheet.details")}>
        <dl>
          <DetailRow label={t("sheet.window")}>{formatWindow(r.start_at, r.end_at, locale)}</DetailRow>
          <DetailRow label={t("sheet.price")}>{formatVnd(r.price_amount, r.currency, locale)}</DetailRow>
        </dl>
        {r.status === "rejected" && r.moderation_note && (
          <p
            className="mt-2.5 rounded-lg px-3 py-2 type-caption"
            style={{ background: "var(--content-danger-soft)", color: "var(--content-danger)" }}
            role="alert"
          >
            {t("rejectReasonInline", { reason: r.moderation_note })}
          </p>
        )}
      </DetailSheetSection>

      <DetailSheetSection>
        <Link
          href={r.target_type === "job" ? `/partner/jobs/${r.target_id}` : `/partner/events/${r.target_id}`}
          className="inline-flex items-center gap-1.5 type-small font-semibold text-[var(--brand-primary)] hover:underline"
        >
          <ExternalLink className="size-4" strokeWidth={1.8} />
          {t("sheet.openTarget")}
        </Link>
      </DetailSheetSection>
    </DetailSheet>
  );
}
