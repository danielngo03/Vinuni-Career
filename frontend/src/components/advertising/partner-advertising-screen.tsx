"use client";

import { useMemo, useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import { useInfiniteQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Megaphone,
  Plus,
  LightbulbFilament,
  ShieldWarning,
  SignIn,
  Sparkle,
  WarningCircle,
  Clock,
  CheckCircle,
  Image as ImageIcon,
  Broadcast,
  Hourglass,
  PencilSimple as PencilSimpleIcon,
} from "@phosphor-icons/react";
import {
  Button,
  DataTable,
  EmptyState,
  Modal,
  StatusBadge,
  useToast,
  type Column,
} from "@/components/ui";
import { cn } from "@/lib/utils";
import { PageHeader } from "@/components/layout/page-header";
import { PlacementFormModal } from "./placement-form-modal";
import { CreativeManagerModal } from "./creative-manager-modal";
import {
  useAdvertisingLabels,
  PLACEMENT_STATUS_TONE,
  PLACEMENT_TYPE_TONE,
} from "@/lib/advertising/labels";
import { daysUntil, formatVnd, formatWindow } from "@/lib/advertising/format";
import { useApiErrorMessage } from "@/lib/auth/use-api-error";
import { ApiError, advertisingApi, type Placement } from "@/lib/api";

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

const EDITABLE = new Set(["draft", "rejected"]);
const CANCELLABLE = new Set(["pending_approval", "approved", "active"]);
/** Creatives can be staged/managed while the campaign is not terminal. */
const MANAGE_CREATIVES = new Set([
  "draft",
  "pending_approval",
  "approved",
  "active",
]);

type AdInsightKey =
  | "insightPendingApproval"
  | "insightActiveCampaigns"
  | "insightDraftsPending"
  | "insightGetStarted";

function deriveAdInsights(rows: { status: string }[]): AdInsightKey[] {
  const out: AdInsightKey[] = [];
  const active = rows.filter((r) => r.status === "active").length;
  const pending = rows.filter((r) => r.status === "pending_approval").length;
  const drafts = rows.filter((r) => r.status === "draft").length;

  if (pending > 0) out.push("insightPendingApproval");
  if (active > 0) out.push("insightActiveCampaigns");
  if (drafts > 0 && pending === 0) out.push("insightDraftsPending");
  if (out.length === 0 && rows.length === 0) out.push("insightGetStarted");
  return out.slice(0, 3);
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

  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<Placement | null>(null);
  const [cancelTarget, setCancelTarget] = useState<Placement | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<Placement | null>(null);
  const [creativeTargetId, setCreativeTargetId] = useState<string | null>(null);

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

  const rows: Placement[] = useMemo(
    () => query.data?.pages.flatMap((p) => p.data) ?? [],
    [query.data],
  );
  const adInsights = useMemo(() => (!query.isPending && !query.isError ? deriveAdInsights(rows) : []), [rows, query.isPending, query.isError]);

  /** Targets with a live (non-terminal) placement — blocked in the create picker. */
  const inflightTargetIds = useMemo(() => {
    const s = new Set<string>();
    for (const p of rows) {
      if (["pending_approval", "approved", "active"].includes(p.status)) {
        s.add(p.target_id);
      }
    }
    return s;
  }, [rows]);

  /** Re-derived from live rows so the creative modal stays fresh after a mutation. */
  const creativeTarget = creativeTargetId
    ? (rows.find((r) => r.id === creativeTargetId) ?? null)
    : null;

  function refresh() {
    void qc.invalidateQueries({ queryKey: ["advertising", "placements"] });
  }

  function handleMutationError(e: unknown) {
    if (e instanceof ApiError && e.isConflict) {
      toast.show({
        tone: "error",
        title: t("errors.conflictTitle"),
        description: t("errors.conflictBody"),
      });
      refresh();
      return;
    }
    toast.show({ tone: "error", title: getMessage(e) });
  }

  const cancel = useMutation({
    mutationFn: (p: Placement) => advertisingApi.cancelPlacement(p.id, p.version),
    onSuccess: () => {
      setCancelTarget(null);
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
      onClick={() => {
        setEditing(null);
        setFormOpen(true);
      }}
    >
      <Plus aria-hidden weight="bold" className="size-4" />
      {t("newPlacement")}
    </Button>
  );

  /* ---- Permission / auth states ---- */
  if (query.isError && query.error instanceof ApiError) {
    const err = query.error;
    if (err.isPermissionError || err.isAuthError) {
      return (
        <>
          <PageHeader title={t("partnerTitle")} description={t("partnerSubtitle")} />
          <EmptyState
            kind={err.isPermissionError ? "permission" : "auth"}
            icon={err.isPermissionError ? ShieldWarning : SignIn}
            title={
              err.isPermissionError ? tStates("permissionTitle") : tStates("authTitle")
            }
            description={
              err.isPermissionError ? t("permissionBody") : tStates("authBody")
            }
          />
        </>
      );
    }
  }

  const columns: Column<Placement>[] = [
    {
      key: "target",
      header: t("colTarget"),
      cell: (r) => (
        <div className="min-w-0">
          <p className="truncate font-semibold text-[var(--text-primary)]">
            {r.target_title ?? t("targetUnavailable")}
          </p>
          <p className="truncate text-xs text-[var(--text-secondary)]">
            {labels.targetType(r.target_type, r.target_type_label)}
          </p>
        </div>
      ),
    },
    {
      key: "type",
      header: t("colType"),
      cell: (r) => (
        <StatusBadge tone={PLACEMENT_TYPE_TONE[r.placement_type] ?? "info"}>
          {labels.placementType(r.placement_type, r.placement_type_label)}
        </StatusBadge>
      ),
    },
    {
      key: "price",
      header: t("colPrice"),
      cell: (r) => (
        <span className="font-medium text-[var(--text-primary)]">
          {formatVnd(r.price_amount, r.currency, locale)}
        </span>
      ),
    },
    {
      key: "window",
      header: t("colWindow"),
      cell: (r) => {
        const days = r.status === "active" ? daysUntil(r.end_at) : null;
        return (
          <div className="text-[var(--text-secondary)]">
            <span className="text-xs">
              {formatWindow(r.start_at, r.end_at, locale)}
            </span>
            {r.status === "active" && days != null && days >= 0 && (
              <span
                className={`mt-0.5 flex items-center gap-1 text-xs font-semibold ${
                  days <= 1 ? "text-[var(--brand-red)]" : "text-[var(--teal-600)]"
                }`}
              >
                {days <= 1 ? (
                  <Clock aria-hidden weight="duotone" className="size-3.5" />
                ) : (
                  <CheckCircle aria-hidden weight="duotone" className="size-3.5" />
                )}
                {days <= 1 ? t("endingSoon") : t("daysLeft", { count: days })}
              </span>
            )}
          </div>
        );
      },
    },
    {
      key: "status",
      header: t("colStatus"),
      cell: (r) => (
        <div className="flex flex-col items-start gap-1">
          <StatusBadge tone={PLACEMENT_STATUS_TONE[r.status] ?? "info"}>
            {labels.status(r.status, r.status_label)}
          </StatusBadge>
          {r.status === "approved" && !r.is_paid && (
            <span className="text-[11px] font-medium text-[var(--amber-700)]">
              {t("awaitingPayment")}
            </span>
          )}
          {r.status === "rejected" && r.moderation_note && (
            <span className="max-w-[16rem] text-[11px] text-[var(--text-muted)]">
              {t("rejectReasonInline", { reason: r.moderation_note })}
            </span>
          )}
          {r.missing_primary_slots && r.missing_primary_slots.length > 0 && (
            <span className="flex items-center gap-1 text-[11px] font-semibold text-[var(--amber-700)]">
              <ImageIcon aria-hidden weight="duotone" className="size-3.5" />
              {t("assetRequired")}
            </span>
          )}
        </div>
      ),
    },
    {
      key: "actions",
      header: "",
      align: "right",
      cell: (r) => (
        <div className="flex items-center justify-end gap-1">
          {MANAGE_CREATIVES.has(r.status) && (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setCreativeTargetId(r.id)}
            >
              <ImageIcon aria-hidden weight="duotone" className="size-4" />
              {t("creatives")}
            </Button>
          )}
          {EDITABLE.has(r.status) && (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => {
                setEditing(r);
                setFormOpen(true);
              }}
            >
              {r.status === "rejected" ? t("editResubmit") : t("editSend")}
            </Button>
          )}
          {EDITABLE.has(r.status) && (
            <Button variant="ghost" size="sm" onClick={() => setDeleteTarget(r)}>
              {tc("delete")}
            </Button>
          )}
          {CANCELLABLE.has(r.status) && (
            <Button variant="ghost" size="sm" onClick={() => setCancelTarget(r)}>
              {t("cancelPlacement")}
            </Button>
          )}
        </div>
      ),
    },
  ];

  return (
    <>
      <PageHeader
        title={t("partnerTitle")}
        description={t("partnerSubtitle")}
        actions={newButton}
      />

      {/* Campaign health tiles */}
      {rows.length > 0 && (
        <div className="mb-5 grid grid-cols-3 gap-3">
          <div className="rounded-2xl border border-[var(--border-default)] bg-white px-4 py-3.5 shadow-[0_2px_12px_rgba(11,34,57,0.06)] transition-all hover:-translate-y-0.5">
            <div className="mb-2.5 flex size-9 items-center justify-center rounded-xl icon-chip-success shadow-sm">
              <Broadcast aria-hidden weight="duotone" className="size-4.5 text-white" />
            </div>
            <p className="text-2xl font-black tracking-tight text-[var(--text-primary)]">
              {rows.filter((r) => r.status === "active").length}
            </p>
            <p className="mt-0.5 text-xs font-medium text-[var(--text-secondary)]">{t("statActiveCampaigns")}</p>
          </div>
          <div className="rounded-2xl border border-[var(--border-default)] bg-white px-4 py-3.5 shadow-[0_2px_12px_rgba(11,34,57,0.06)] transition-all hover:-translate-y-0.5">
            <div className="mb-2.5 flex size-9 items-center justify-center rounded-xl icon-chip-warning shadow-sm">
              <Hourglass aria-hidden weight="duotone" className="size-4.5 text-white" />
            </div>
            <p className="text-2xl font-black tracking-tight text-[var(--text-primary)]">
              {rows.filter((r) => r.status === "pending_approval").length}
            </p>
            <p className="mt-0.5 text-xs font-medium text-[var(--text-secondary)]">{t("statPendingApproval")}</p>
          </div>
          <div className="rounded-2xl border border-[var(--border-default)] bg-white px-4 py-3.5 shadow-[0_2px_12px_rgba(11,34,57,0.06)] transition-all hover:-translate-y-0.5">
            <div className="mb-2.5 flex size-9 items-center justify-center rounded-xl icon-chip-neutral shadow-sm">
              <PencilSimpleIcon aria-hidden weight="duotone" className="size-4.5 text-white" />
            </div>
            <p className="text-2xl font-black tracking-tight text-[var(--text-primary)]">
              {rows.filter((r) => r.status === "draft").length}
            </p>
            <p className="mt-0.5 text-xs font-medium text-[var(--text-secondary)]">{t("statDrafts")}</p>
          </div>
        </div>
      )}

      {/* AI Campaign Insights */}
      {adInsights.length > 0 && (
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
            {adInsights.map((key) => (
              <li key={key} className="flex items-start gap-2 text-xs text-[var(--text-secondary)]">
                <LightbulbFilament aria-hidden weight="duotone" className="mt-0.5 size-3.5 shrink-0 text-[var(--ai-accent)]" />
                {t(key)}
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* Disclosure notice — the label is non-removable. */}
      <div className="mb-4 flex items-start gap-2.5 rounded-xl border border-[var(--blue-200)] bg-[var(--blue-50)] px-3.5 py-3 text-sm text-[var(--text-secondary)]">
        <span className="flex size-6 shrink-0 items-center justify-center rounded-md icon-chip-primary shadow-sm">
          <Megaphone aria-hidden weight="duotone" className="size-3.5 text-white" />
        </span>
        <p>{t("disclosureNotice")}</p>
      </div>

      {/* Status filter tab chips */}
      <div className="mb-4 flex flex-wrap gap-2" role="group" aria-label={t("filterStatusLabel")}>
        {STATUS_FILTERS.map((s) => (
          <button
            key={s}
            onClick={() => setStatusFilter(s)}
            aria-pressed={statusFilter === s}
            className={cn(
              "inline-flex items-center rounded-full border px-3.5 py-1.5 text-xs font-semibold transition-all focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--brand-primary)]",
              statusFilter === s
                ? "border-[var(--brand-primary)]/30 bg-[var(--brand-primary)] text-white shadow-sm shadow-[var(--brand-primary)]/20"
                : "border-[var(--border-default)] bg-white text-[var(--text-secondary)] hover:bg-white hover:text-[var(--text-primary)]",
            )}
          >
            {s === "all" ? t("filterAllStatuses") : labels.status(s)}
          </button>
        ))}
      </div>

      {query.isError &&
      !(
        query.error instanceof ApiError &&
        (query.error.isPermissionError || query.error.isAuthError)
      ) ? (
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
          <DataTable
            columns={columns}
            rows={rows}
            getRowId={(r) => r.id}
            loading={query.isPending}
            caption={t("partnerTitle")}
            empty={{
              kind: "empty",
              icon: Megaphone,
              title:
                statusFilter === "all"
                  ? t("emptyTitle")
                  : t("emptyFilterTitle"),
              description:
                statusFilter === "all"
                  ? t("emptyBody")
                  : t("emptyFilterBody"),
              action: statusFilter === "all" ? newButton : undefined,
            }}
          />
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

      {/* Create / edit */}
      <PlacementFormModal
        open={formOpen}
        onClose={() => setFormOpen(false)}
        placement={editing}
        inflightTargetIds={inflightTargetIds}
      />

      {/* Per-placement creative manager (upload / preview / moderation status) */}
      <CreativeManagerModal
        open={creativeTarget !== null}
        onClose={() => setCreativeTargetId(null)}
        placement={creativeTarget}
      />

      {/* Cancel confirmation */}
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
            <Button
              variant="danger"
              loading={cancel.isPending}
              onClick={() => cancelTarget && cancel.mutate(cancelTarget)}
            >
              {t("cancelConfirm")}
            </Button>
          </>
        }
      >
        <p className="text-sm text-[var(--text-secondary)]">
          {cancelTarget?.status === "active"
            ? t("cancelActiveNote")
            : t("cancelNote")}
        </p>
      </Modal>

      {/* Delete confirmation */}
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
            <Button
              variant="danger"
              loading={remove.isPending}
              onClick={() => deleteTarget && remove.mutate(deleteTarget)}
            >
              {tc("delete")}
            </Button>
          </>
        }
      >
        <p className="text-sm text-[var(--text-secondary)]">{t("deleteNote")}</p>
      </Modal>
    </>
  );
}
