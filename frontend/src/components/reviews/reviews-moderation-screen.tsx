"use client";

import { useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ChatCircleText,
  LightbulbFilament,
  ShieldWarning,
  SignIn,
  CheckCircle,
  XCircle,
  ArrowCounterClockwise,
  Hourglass,
  Flag,
  Sparkle,
} from "@phosphor-icons/react";
import {
  Button,
  DataTable,
  EmptyState,
  Modal,
  Select,
  StatusBadge,
  Textarea,
  useToast,
  type Column,
} from "@/components/ui";
import { cn } from "@/lib/utils";
import { PageHeader } from "@/components/layout/page-header";
import { StarDisplay } from "./star-rating";
import { useApiErrorMessage } from "@/lib/auth/use-api-error";
import { ApiError, reviewsApi, type ModerationReview } from "@/lib/api";

type ReviewModerationInsightKey =
  | "insightFlaggedUrgent"
  | "insightPendingReviews"
  | "insightQueueClear"
  | "insightMixedQueue";

function deriveReviewModerationInsights(
  pending: number | undefined,
  flagged: number | undefined,
): ReviewModerationInsightKey[] {
  const p = pending ?? 0;
  const f = flagged ?? 0;
  const out: ReviewModerationInsightKey[] = [];
  if (f > 0) out.push("insightFlaggedUrgent");
  if (p > 2) out.push("insightPendingReviews");
  if (p === 0 && f === 0) out.push("insightQueueClear");
  if (p > 0 && f > 0) out.push("insightMixedQueue");
  return out.slice(0, 2);
}

const REMOVAL_REASONS = [
  "pii",
  "harassment",
  "discrimination",
  "spam",
  "off_topic",
  "false_claim",
] as const;

const TONE: Record<string, "pending" | "active" | "rejected" | "info"> = {
  pending: "pending",
  published: "active",
  flagged: "info",
  removed: "rejected",
};

export function ReviewsModerationScreen() {
  const t = useTranslations("reviewsModeration");
  const tStates = useTranslations("states");
  const tc = useTranslations("common");
  const locale = useLocale();
  const toast = useToast();
  const qc = useQueryClient();
  const getMessage = useApiErrorMessage();

  const [statusFilter, setStatusFilter] = useState<string>("pending");
  const [removing, setRemoving] = useState<ModerationReview | null>(null);
  const [reason, setReason] = useState<string>(REMOVAL_REASONS[0]);
  const [note, setNote] = useState("");

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
      refresh();
    },
    onError: onErr,
  });
  const restore = useMutation({
    mutationFn: (r: ModerationReview) => reviewsApi.restore(r.id, locale),
    onSuccess: () => {
      toast.show({ tone: "success", title: t("restoredToast") });
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
      setNote("");
      refresh();
    },
    onError: onErr,
  });

  if (query.isError && query.error instanceof ApiError) {
    const err = query.error;
    if (err.isPermissionError || err.isAuthError) {
      return (
        <>
          <PageHeader title={t("title")} description={t("subtitle")} />
          <EmptyState
            kind={err.isPermissionError ? "permission" : "auth"}
            icon={err.isPermissionError ? ShieldWarning : SignIn}
            title={
              err.isPermissionError
                ? tStates("permissionTitle")
                : tStates("authTitle")
            }
            description={
              err.isPermissionError ? t("permissionBody") : tStates("authBody")
            }
          />
        </>
      );
    }
  }

  const rows = query.data?.items ?? [];
  const counts = query.data?.counts;

  const columns: Column<ModerationReview>[] = [
    {
      key: "review",
      header: t("colReview"),
      cell: (r) => (
        <div className="min-w-0 max-w-md">
          <p className="truncate font-semibold text-[var(--text-primary)]">
            {r.title}
          </p>
          <p className="truncate text-xs text-[var(--text-muted)]">
            {r.author_name} · {r.trust_label}
          </p>
          <p className="mt-0.5 line-clamp-2 text-xs text-[var(--text-secondary)]">
            {r.body}
          </p>
        </div>
      ),
    },
    {
      key: "overall",
      header: t("colRating"),
      cell: (r) => <StarDisplay value={r.ratings.overall} size={14} />,
    },
    {
      key: "status",
      header: t("colStatus"),
      cell: (r) => (
        <div className="flex flex-col gap-1">
          <StatusBadge tone={TONE[r.status] ?? "info"}>
            {r.status_label}
          </StatusBadge>
          {r.report_count > 0 && (
            <span className="text-xs text-[var(--brand-red)]">
              {t("reports", { count: r.report_count })}
            </span>
          )}
        </div>
      ),
    },
    {
      key: "actions",
      header: "",
      cell: (r) => (
        <div className="flex justify-end gap-1.5">
          {(r.status === "pending" || r.status === "flagged") && (
            <Button
              size="sm"
              variant="secondary"
              onClick={() => publish.mutate(r)}
              loading={publish.isPending}
            >
              <CheckCircle aria-hidden weight="duotone" className="size-4" />
              {t("publish")}
            </Button>
          )}
          {r.status === "removed" && (
            <Button
              size="sm"
              variant="secondary"
              onClick={() => restore.mutate(r)}
              loading={restore.isPending}
            >
              <ArrowCounterClockwise aria-hidden weight="duotone" className="size-4" />
              {t("restore")}
            </Button>
          )}
          {r.status !== "removed" && (
            <Button size="sm" variant="ghost" onClick={() => setRemoving(r)}>
              <XCircle aria-hidden weight="duotone" className="size-4" />
              {t("remove")}
            </Button>
          )}
        </div>
      ),
    },
  ];

  return (
    <>
      <PageHeader title={t("title")} description={t("subtitle")} />

      <div className="mb-5 grid grid-cols-2 gap-3 sm:max-w-md">
        <Stat
          label={t("pendingCount")}
          value={counts?.pending}
          icon={<Hourglass aria-hidden weight="duotone" className="size-5 text-white" />}
          iconBg="icon-chip-warning"
        />
        <Stat
          label={t("flaggedCount")}
          value={counts?.flagged}
          icon={<Flag aria-hidden weight="duotone" className="size-5 text-white" />}
          iconBg="icon-chip-danger"
        />
      </div>

      {(() => {
        const insights = !query.isPending ? deriveReviewModerationInsights(counts?.pending, counts?.flagged) : [];
        if (insights.length === 0) return null;
        return (
          <section
            className="mb-5 rounded-2xl border border-[var(--ai-accent)]/25 bg-gradient-to-br from-[var(--ai-accent-soft)] to-white/60 p-4 "
            aria-label={t("aiInsightsTitle")}
          >
            <h2 className="mb-2.5 flex items-center gap-2 text-sm font-bold text-[var(--text-primary)]">
              <span className="flex size-6 shrink-0 items-center justify-center rounded-lg icon-chip-info shadow-sm">
                <Sparkle aria-hidden weight="duotone" className="size-3.5 text-white" />
              </span>
              {t("aiInsightsTitle")}
            </h2>
            <ul className="space-y-1.5">
              {insights.map((key) => (
                <li key={key} className="flex items-start gap-2 text-xs text-[var(--text-secondary)]">
                  <LightbulbFilament aria-hidden weight="duotone" className="mt-0.5 size-3.5 shrink-0 text-[var(--ai-accent)]" />
                  {t(key)}
                </li>
              ))}
            </ul>
          </section>
        );
      })()}

      <div className="mb-4 flex flex-wrap gap-2">
        {([
          { value: "pending", label: t("filter.pending"), active: "border-[var(--amber-500)]/30 bg-[var(--amber-600)] text-white shadow-sm" },
          { value: "flagged", label: t("filter.flagged"), active: "border-orange-400/30 bg-orange-500 text-white shadow-sm" },
          { value: "published", label: t("filter.published"), active: "border-[var(--teal-500)]/30 bg-[var(--teal-600)] text-white shadow-sm" },
          { value: "removed", label: t("filter.removed"), active: "border-[var(--red-500)]/30 bg-[var(--red-600)] text-white shadow-sm" },
        ] as const).map(({ value, label, active }) => (
          <button
            key={value}
            type="button"
            onClick={() => setStatusFilter(value)}
            aria-pressed={statusFilter === value}
            className={cn(
              "inline-flex items-center rounded-full border px-3.5 py-1.5 text-xs font-semibold transition-all focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--brand-primary)]",
              statusFilter === value
                ? active
                : "border-[var(--border-default)] bg-[var(--surface-card)] text-[var(--text-secondary)] hover:bg-[var(--surface-card)] hover:text-[var(--text-primary)]",
            )}
          >
            {label}
          </button>
        ))}
      </div>

      <DataTable
        columns={columns}
        rows={rows}
        getRowId={(r) => r.id}
        loading={query.isPending}
        caption={t("title")}
        empty={{
          kind: "empty",
          icon: ChatCircleText,
          title: t("empty"),
          description: t("emptyBody"),
        }}
      />

      <Modal
        open={removing !== null}
        onClose={() => setRemoving(null)}
        title={t("removeTitle")}
        size="sm"
        closeLabel={tc("close")}
      >
        {removing && (
          <div className="space-y-3">
            <p className="text-sm text-[var(--text-secondary)]">
              {t("removePolicyNote")}
            </p>
            <div>
              <Select
                label={t("reasonLabel")}
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                options={REMOVAL_REASONS.map((rc) => ({
                  value: rc,
                  label: t(`reason.${rc}`),
                }))}
              />
            </div>
            <Textarea
              aria-label={t("noteLabel")}
              value={note}
              onChange={(e) => setNote(e.target.value)}
              rows={2}
              placeholder={t("notePlaceholder")}
            />
            <div className="flex justify-end gap-2">
              <Button variant="ghost" onClick={() => setRemoving(null)}>
                {tc("cancel")}
              </Button>
              <Button
                variant="danger"
                onClick={() => remove.mutate(removing)}
                loading={remove.isPending}
              >
                {t("remove")}
              </Button>
            </div>
          </div>
        )}
      </Modal>
    </>
  );
}

function Stat({
  label,
  value,
  icon,
  iconBg = "icon-chip-primary",
}: {
  label: string;
  value?: number;
  icon: React.ReactNode;
  iconBg?: string;
}) {
  return (
    <div className="rounded-2xl border border-[var(--border-default)] bg-[var(--surface-card)] px-5 py-4 shadow-[0_2px_16px_rgba(11,34,57,0.06)] transition-all hover:-translate-y-0.5 hover:shadow-[0_6px_24px_rgba(11,34,57,0.10)]">
      <div className={`mb-3 flex size-11 items-center justify-center rounded-xl shadow-sm ${iconBg}`}>
        {icon}
      </div>
      <p className="text-3xl font-black tracking-tight text-[var(--text-primary)]">
        {value ?? "—"}
      </p>
      <p className="mt-1 text-xs font-medium text-[var(--text-secondary)]">{label}</p>
    </div>
  );
}
