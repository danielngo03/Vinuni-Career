"use client";

import * as React from "react";
import { useLocale, useTranslations } from "next-intl";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  CheckCircle2,
  Flag,
  Hourglass,
  MessageSquare,
  RotateCcw,
  XCircle,
} from "lucide-react";
import { Button, Modal, Select, Textarea, useToast } from "@/components/ui";
import {
  DataTable,
  DetailSheet,
  DetailSheetSection,
  DetailRow,
  EmptyState,
  FilterBar,
  KpiTile,
  StatusChip,
  type ChipTone,
  type ColumnDef,
} from "@/components/kit";
import { PageHeader } from "@/components/layout/page-header";
import { cn } from "@/lib/utils";
import { StarDisplay } from "./star-rating";
import { formatDateTime } from "@/lib/format";
import { useApiErrorMessage } from "@/lib/auth/use-api-error";
import { ApiError, reviewsApi, type ModerationReview } from "@/lib/api";

const REMOVAL_REASONS = [
  "pii",
  "harassment",
  "discrimination",
  "spam",
  "off_topic",
  "false_claim",
] as const;

const STATUS_TONE: Record<string, ChipTone> = {
  pending: "warning",
  published: "success",
  flagged: "info",
  removed: "danger",
};

const STATUS_FILTERS = ["pending", "flagged", "published", "removed"] as const;

const RATING_KEYS = [
  "work_life_balance",
  "culture_values",
  "compensation",
  "career_growth",
  "interview_experience",
] as const;

export function ReviewsModerationScreen() {
  const t = useTranslations("reviewsModeration");
  const tStates = useTranslations("states");
  const tc = useTranslations("common");
  const locale = useLocale();
  const toast = useToast();
  const qc = useQueryClient();
  const getMessage = useApiErrorMessage();

  const [statusFilter, setStatusFilter] = React.useState<string>("pending");
  const [selected, setSelected] = React.useState<ModerationReview | null>(null);
  const [removing, setRemoving] = React.useState<ModerationReview | null>(null);
  const [reason, setReason] = React.useState<string>(REMOVAL_REASONS[0]);
  const [note, setNote] = React.useState("");

  const query = useQuery({
    queryKey: ["admin", "reviews", statusFilter, locale],
    queryFn: () => reviewsApi.moderationQueue(statusFilter, locale),
    retry: false,
  });

  function refresh() {
    void qc.invalidateQueries({ queryKey: ["admin", "reviews"] });
  }
  function onErr(e: unknown) {
    toast.show({ tone: "error", title: getMessage(e) });
  }

  const publish = useMutation({
    mutationFn: (r: ModerationReview) => reviewsApi.publish(r.id, locale),
    onSuccess: () => {
      toast.show({ tone: "success", title: t("publishedToast") });
      setSelected(null);
      refresh();
    },
    onError: onErr,
  });
  const restore = useMutation({
    mutationFn: (r: ModerationReview) => reviewsApi.restore(r.id, locale),
    onSuccess: () => {
      toast.show({ tone: "success", title: t("restoredToast") });
      setSelected(null);
      refresh();
    },
    onError: onErr,
  });
  const remove = useMutation({
    mutationFn: (r: ModerationReview) =>
      reviewsApi.removeByModerator(r.id, reason, note.trim() || undefined, locale),
    onSuccess: () => {
      toast.show({ tone: "success", title: t("removedToast") });
      setRemoving(null);
      setSelected(null);
      setNote("");
      refresh();
    },
    onError: onErr,
  });

  const isPermissionError =
    query.isError &&
    query.error instanceof ApiError &&
    (query.error.isPermissionError || query.error.isAuthError);

  const rows = query.data?.items ?? [];
  const counts = query.data?.counts;

  const columns: ColumnDef<ModerationReview, unknown>[] = [
    {
      accessorKey: "title",
      header: t("colReview"),
      cell: ({ row }) => (
        <div className="min-w-0 max-w-md">
          <p className="truncate font-semibold text-foreground">{row.original.title}</p>
          <p className="truncate type-caption text-muted-foreground">
            {row.original.author_name} · {row.original.trust_label}
          </p>
          <p className="mt-0.5 line-clamp-2 type-small text-muted-foreground">{row.original.body}</p>
        </div>
      ),
    },
    {
      id: "overall",
      header: t("colRating"),
      enableSorting: false,
      cell: ({ row }) => <StarDisplay value={row.original.ratings.overall} size={14} />,
    },
    {
      accessorKey: "status",
      header: t("colStatus"),
      cell: ({ row }) => (
        <div className="flex flex-col gap-1">
          <StatusChip tone={STATUS_TONE[row.original.status] ?? "neutral"}>
            {row.original.status_label}
          </StatusChip>
          {row.original.report_count > 0 && (
            <span className="type-caption font-medium text-[var(--content-danger)]">
              {t("reports", { count: row.original.report_count })}
            </span>
          )}
        </div>
      ),
    },
    {
      id: "actions",
      header: "",
      enableSorting: false,
      meta: { align: "right" },
      cell: ({ row }) => (
        <Button variant="ghost" size="sm" onClick={() => setSelected(row.original)}>
          {t("review")}
        </Button>
      ),
    },
  ];

  return (
    <>
      <PageHeader title={t("title")} description={t("subtitle")} />

      {isPermissionError ? (
        <EmptyState
          kind={query.error instanceof ApiError && query.error.isPermissionError ? "permission" : "auth"}
          title={
            query.error instanceof ApiError && query.error.isPermissionError
              ? tStates("permissionTitle")
              : tStates("authTitle")
          }
          description={
            query.error instanceof ApiError && query.error.isPermissionError
              ? t("permissionBody")
              : tStates("authBody")
          }
        />
      ) : (
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-3 sm:max-w-md">
            <KpiTile label={t("pendingCount")} value={counts ? String(counts.pending) : "—"} icon={Hourglass} />
            <KpiTile label={t("flaggedCount")} value={counts ? String(counts.flagged) : "—"} icon={Flag} />
          </div>

          <FilterBar>
            <div className="flex flex-wrap gap-1.5" role="group" aria-label={t("filterLabel")}>
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
                    {t(`filter.${s}`)}
                  </button>
                );
              })}
            </div>
          </FilterBar>

          {query.isError && !isPermissionError ? (
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
            <DataTable
              columns={columns}
              data={rows}
              getRowId={(r) => r.id}
              loading={query.isPending}
              onRowClick={(r) => setSelected(r)}
              activeRowId={selected?.id ?? undefined}
              empty={
                <EmptyState kind="empty" icon={MessageSquare} title={t("empty")} description={t("emptyBody")} />
              }
            />
          )}
        </div>
      )}

      {/* Review detail sheet */}
      <ReviewDetailSheet
        review={selected}
        onClose={() => setSelected(null)}
        onPublish={() => selected && publish.mutate(selected)}
        onRestore={() => selected && restore.mutate(selected)}
        onRemove={() => {
          if (selected) {
            setReason(REMOVAL_REASONS[0]);
            setNote("");
            setRemoving(selected);
          }
        }}
        publishing={publish.isPending}
        restoring={restore.isPending}
      />

      {/* Remove confirmation */}
      <Modal
        open={removing !== null}
        onClose={() => setRemoving(null)}
        title={t("removeTitle")}
        size="sm"
        closeLabel={tc("close")}
      >
        {removing && (
          <div className="space-y-3">
            <p className="text-sm text-muted-foreground">{t("removePolicyNote")}</p>
            <Select
              label={t("reasonLabel")}
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              options={REMOVAL_REASONS.map((rc) => ({ value: rc, label: t(`reason.${rc}`) }))}
            />
            <Textarea
              label={t("noteLabel")}
              value={note}
              onChange={(e) => setNote(e.target.value)}
              rows={2}
              placeholder={t("notePlaceholder")}
            />
            <div className="flex justify-end gap-2">
              <Button variant="ghost" onClick={() => setRemoving(null)}>
                {tc("cancel")}
              </Button>
              <Button variant="danger" onClick={() => remove.mutate(removing)} loading={remove.isPending}>
                {t("remove")}
              </Button>
            </div>
          </div>
        )}
      </Modal>
    </>
  );
}

/* -------------------------------------------------------------------------- */
/* Review detail sheet                                                         */
/* -------------------------------------------------------------------------- */

function ReviewDetailSheet({
  review,
  onClose,
  onPublish,
  onRestore,
  onRemove,
  publishing,
  restoring,
}: {
  review: ModerationReview | null;
  onClose: () => void;
  onPublish: () => void;
  onRestore: () => void;
  onRemove: () => void;
  publishing: boolean;
  restoring: boolean;
}) {
  const t = useTranslations("reviewsModeration");
  const tc = useTranslations("common");
  const locale = useLocale();
  const open = review != null;

  const canPublish = review?.status === "pending" || review?.status === "flagged";
  const canRestore = review?.status === "removed";
  const canRemove = review != null && review.status !== "removed";

  return (
    <DetailSheet
      open={open}
      onClose={onClose}
      title={review?.title ?? t("review")}
      subtitle={review ? `${review.author_name} · ${review.trust_label}` : undefined}
      status={
        review ? (
          <>
            <StatusChip tone={STATUS_TONE[review.status] ?? "neutral"}>{review.status_label}</StatusChip>
            {review.report_count > 0 && (
              <StatusChip tone="danger">{t("reports", { count: review.report_count })}</StatusChip>
            )}
          </>
        ) : undefined
      }
      width="lg"
      closeLabel={tc("close")}
      footer={
        review ? (
          <>
            {canRemove && (
              <Button variant="ghost" size="sm" onClick={onRemove}>
                <XCircle className="size-4" strokeWidth={1.8} />
                {t("remove")}
              </Button>
            )}
            {canRestore && (
              <Button variant="secondary" size="sm" loading={restoring} onClick={onRestore}>
                <RotateCcw className="size-4" strokeWidth={1.8} />
                {t("restore")}
              </Button>
            )}
            {canPublish && (
              <Button variant="primary" size="sm" loading={publishing} onClick={onPublish}>
                <CheckCircle2 className="size-4" strokeWidth={1.8} />
                {t("publish")}
              </Button>
            )}
          </>
        ) : undefined
      }
    >
      {review && (
        <>
          <DetailSheetSection title={t("sheetRatingsLabel")}>
            <div className="mb-3 flex items-center gap-2">
              <StarDisplay value={review.ratings.overall} size={16} />
              <span className="text-sm font-semibold tabular-nums text-foreground">
                {review.ratings.overall.toFixed(1)}
              </span>
            </div>
            <dl>
              {RATING_KEYS.map((key) => {
                const value = review.ratings[key];
                if (value == null) return null;
                return (
                  <DetailRow key={key} label={t(`rating.${key}`)}>
                    <span className="tabular-nums">{value.toFixed(1)}</span>
                  </DetailRow>
                );
              })}
            </dl>
          </DetailSheetSection>

          <DetailSheetSection title={t("sheetBodyLabel")}>
            <p className="whitespace-pre-wrap text-sm text-foreground">{review.body}</p>
          </DetailSheetSection>

          {(review.pros || review.cons) && (
            <DetailSheetSection>
              {review.pros && (
                <div className="mb-3">
                  <p className="type-caption font-semibold uppercase tracking-wide text-[var(--content-success)]">
                    {t("sheetProsLabel")}
                  </p>
                  <p className="mt-1 whitespace-pre-wrap text-sm text-foreground">{review.pros}</p>
                </div>
              )}
              {review.cons && (
                <div>
                  <p className="type-caption font-semibold uppercase tracking-wide text-[var(--content-danger)]">
                    {t("sheetConsLabel")}
                  </p>
                  <p className="mt-1 whitespace-pre-wrap text-sm text-foreground">{review.cons}</p>
                </div>
              )}
            </DetailSheetSection>
          )}

          {review.partner_response && (
            <DetailSheetSection title={t("sheetPartnerResponseLabel")}>
              <p className="whitespace-pre-wrap text-sm text-foreground">{review.partner_response}</p>
            </DetailSheetSection>
          )}

          <DetailSheetSection>
            <dl>
              <DetailRow label={t("sheetSubmittedLabel")}>
                {formatDateTime(review.created_at, locale)}
              </DetailRow>
            </dl>
          </DetailSheetSection>
        </>
      )}
    </DetailSheet>
  );
}
