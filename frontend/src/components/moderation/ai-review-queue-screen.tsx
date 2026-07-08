"use client";

import { useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowSquareOut,
  Briefcase,
  CalendarBlank,
  CheckCircle,
  Flag,
  ShieldWarning,
  SignIn,
  Sparkle,
  WarningCircle,
  XCircle,
} from "@phosphor-icons/react";
import {
  Button,
  DataTable,
  EmptyState,
  Modal,
  StatusBadge,
  useToast,
  type Column,
  type StatusTone,
} from "@/components/ui";
import { Link } from "@/i18n/navigation";
import { PageHeader } from "@/components/layout/page-header";
import { ModerationTabs } from "@/components/moderation/moderation-tabs";
import { ReasonCodeSelect, SlaBadge } from "@/components/moderation/queue-controls";
import { formatDateTime } from "@/lib/format";
import {
  ApiError,
  aiReviewQueueApi,
  type AiReviewQueueItem,
  type ModerationReasonCode,
} from "@/lib/api";
import { useApiErrorMessage } from "@/lib/auth/use-api-error";

/** Lifecycle status → badge tone (color + label, never color alone). */
const STATUS_TONE: Record<string, StatusTone> = {
  pending_review: "pending",
  active: "active",
  published: "active",
  rejected: "rejected",
  closed: "closed",
  cancelled: "closed",
  expired: "closed",
  draft: "draft",
};

type Decision = "uphold" | "dismiss";

/**
 * AI human-review queue (B-579). Lists jobs + events that AI/rule moderation
 * FLAGGED and shows the user-safe flag reason, age/SLA, and status. The AI flag
 * is advisory: a moderator upholds it (rejects the item) or dismisses it (clears
 * the flag), each requiring a reason. No model/confidence/provider internals are
 * ever surfaced here.
 */
export function AiReviewQueueScreen() {
  const t = useTranslations("aiReviewQueue");
  const tStates = useTranslations("states");
  const tc = useTranslations("common");
  const locale = useLocale();
  const toast = useToast();
  const qc = useQueryClient();
  const getMessage = useApiErrorMessage();

  const [selected, setSelected] = useState<AiReviewQueueItem | null>(null);
  const [decision, setDecision] = useState<Decision | null>(null);
  const [reason, setReason] = useState("");
  const [reasonCode, setReasonCode] = useState<ModerationReasonCode | string>(
    "policy_violation",
  );
  const [reasonError, setReasonError] = useState<string | null>(null);

  const query = useQuery({
    queryKey: ["university", "ai-review-queue", locale],
    queryFn: () => aiReviewQueueApi.list({ locale }),
    retry: false,
  });

  function refresh() {
    // Prefix match invalidates both the list and the /counts badge query.
    void qc.invalidateQueries({ queryKey: ["university", "ai-review-queue"] });
  }

  function closeModal() {
    setDecision(null);
    setSelected(null);
    setReason("");
    setReasonError(null);
  }

  function openDecision(item: AiReviewQueueItem, kind: Decision) {
    setSelected(item);
    setDecision(kind);
    setReason("");
    setReasonError(null);
    if (kind === "uphold") {
      const known = KNOWN_REASON_CODES.has(item.flag_reason_code ?? "");
      setReasonCode(known ? (item.flag_reason_code as string) : "policy_violation");
    }
  }

  function handleError(e: unknown) {
    // The item may have already left the queue (decided elsewhere / status moved).
    if (e instanceof ApiError && (e.isConflict || e.isNotFound)) {
      toast.show({
        tone: "error",
        title: t("goneToast"),
        description: t("goneBody"),
      });
      closeModal();
      refresh();
      return;
    }
    toast.show({ tone: "error", title: getMessage(e) });
  }

  const uphold = useMutation({
    mutationFn: (item: AiReviewQueueItem) =>
      aiReviewQueueApi.uphold(
        item.item_type,
        item.id,
        { reason: reason.trim(), reason_code: reasonCode },
        locale,
      ),
    onSuccess: () => {
      closeModal();
      toast.show({ tone: "success", title: t("upheldToast") });
      refresh();
    },
    onError: handleError,
  });

  const dismiss = useMutation({
    mutationFn: (item: AiReviewQueueItem) =>
      aiReviewQueueApi.dismiss(
        item.item_type,
        item.id,
        { reason: reason.trim() },
        locale,
      ),
    onSuccess: () => {
      closeModal();
      toast.show({ tone: "success", title: t("dismissedToast") });
      refresh();
    },
    onError: handleError,
  });

  /* ---- Permission / auth states ---- */
  if (query.isError && query.error instanceof ApiError) {
    const err = query.error;
    if (err.isPermissionError || err.isAuthError) {
      return (
        <>
          <PageHeader title={t("title")} description={t("subtitle")} />
          <ModerationTabs />
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

  function submit() {
    if (!selected || !decision) return;
    if (!reason.trim()) {
      setReasonError(t("reasonRequired"));
      return;
    }
    if (decision === "uphold") uphold.mutate(selected);
    else dismiss.mutate(selected);
  }

  const columns: Column<AiReviewQueueItem>[] = [
    {
      key: "item",
      header: t("colItem"),
      cell: (r) => {
        const Icon = r.item_type === "job" ? Briefcase : CalendarBlank;
        return (
          <div className="min-w-0">
            <p className="truncate font-semibold text-[var(--text-primary)]">
              {r.title}
            </p>
            <span className="mt-1 inline-flex items-center gap-1 rounded-full border border-[var(--border-default)] bg-[var(--bg-subtle)] px-2 py-0.5 text-xs font-medium text-[var(--text-secondary)]">
              <Icon aria-hidden weight="duotone" className="size-3.5" />
              {t(`type.${r.item_type}`)}
            </span>
          </div>
        );
      },
    },
    {
      key: "flag",
      header: t("colFlag"),
      cell: (r) => (
        <div className="min-w-0 max-w-xs">
          <StatusBadge tone="featured">
            <Flag aria-hidden weight="bold" className="size-3" />
            {r.flag_reason_label || t("flagGeneric")}
          </StatusBadge>
          {r.flag_note && (
            <p className="mt-1 line-clamp-2 text-xs text-[var(--text-secondary)]">
              {r.flag_note}
            </p>
          )}
        </div>
      ),
    },
    {
      key: "queue",
      header: t("colQueue"),
      cell: (r) => (
        <div className="flex flex-col items-start gap-1">
          <SlaBadge dueBy={r.due_by} ageHours={r.age_hours} isOverdue={r.is_overdue} />
          {r.flagged_at && (
            <span className="text-xs text-[var(--text-muted)]">
              {formatDateTime(r.flagged_at, locale)}
            </span>
          )}
        </div>
      ),
    },
    {
      key: "status",
      header: t("colStatus"),
      cell: (r) => (
        <StatusBadge tone={STATUS_TONE[r.status] ?? "info"}>
          {r.status_label}
        </StatusBadge>
      ),
    },
    {
      key: "actions",
      header: "",
      align: "right",
      cell: (r) => (
        <div className="flex flex-wrap items-center justify-end gap-1">
          <Link
            href={queueHref(r.item_type)}
            className="inline-flex items-center gap-1 rounded-lg px-2.5 py-1.5 text-xs font-semibold text-[var(--text-secondary)] outline-none transition-colors hover:bg-[var(--bg-subtle)] hover:text-[var(--text-primary)] focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/30"
          >
            <ArrowSquareOut aria-hidden weight="bold" className="size-3.5" />
            {t("openRecord")}
          </Link>
          <Button variant="ghost" size="sm" onClick={() => openDecision(r, "dismiss")}>
            <CheckCircle aria-hidden weight="bold" className="size-4" />
            {t("dismiss")}
          </Button>
          <Button variant="danger" size="sm" onClick={() => openDecision(r, "uphold")}>
            <XCircle aria-hidden weight="bold" className="size-4" />
            {t("uphold")}
          </Button>
        </div>
      ),
    },
  ];

  return (
    <>
      <PageHeader title={t("title")} description={t("subtitle")} />
      <ModerationTabs />

      {/* Advisory framing: the AI flag is a signal; the human decides. */}
      {!query.isPending && rows.length > 0 && (
        <section
          aria-label={t("adviceTitle")}
          className="mb-4 flex items-start gap-3 rounded-2xl border border-[var(--border-default)] bg-[var(--surface-card)] p-4"
        >
          <span className="flex size-6 shrink-0 items-center justify-center rounded-lg icon-chip-info shadow-sm">
            <Sparkle aria-hidden weight="duotone" className="size-3.5 text-white" />
          </span>
          <div className="min-w-0">
            <p className="text-sm font-semibold text-[var(--text-primary)]">
              {t("adviceTitle")}
            </p>
            <p className="mt-0.5 text-xs text-[var(--text-secondary)]">
              {t("adviceBody")}
            </p>
          </div>
        </section>
      )}

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
        <DataTable
          columns={columns}
          rows={rows}
          getRowId={(r) => `${r.item_type}:${r.id}`}
          loading={query.isPending}
          caption={t("title")}
          empty={{
            kind: "empty",
            icon: CheckCircle,
            title: t("empty"),
            description: t("emptyBody"),
          }}
        />
      )}

      {/* Uphold — danger; rejects the item. Requires a reason (+ optional code). */}
      <Modal
        open={decision === "uphold"}
        onClose={closeModal}
        title={t("upholdTitle")}
        description={t("upholdBody", { title: selected?.title ?? "" })}
        size="sm"
        closeLabel={tc("close")}
        footer={
          <>
            <Button variant="ghost" onClick={closeModal}>
              {tc("cancel")}
            </Button>
            <Button variant="danger" loading={uphold.isPending} onClick={submit}>
              {t("upholdConfirm")}
            </Button>
          </>
        }
      >
        <div className="space-y-3">
          <ReasonCodeSelect
            id="ai-review-uphold-code"
            value={reasonCode}
            onChange={setReasonCode}
          />
          <ReasonField
            id="ai-review-uphold-reason"
            label={t("reasonLabel")}
            hint={t("reasonHint")}
            value={reason}
            error={reasonError}
            onChange={(v) => {
              setReason(v);
              if (reasonError) setReasonError(null);
            }}
          />
        </div>
      </Modal>

      {/* Dismiss — clears the AI flag. Requires a reason. */}
      <Modal
        open={decision === "dismiss"}
        onClose={closeModal}
        title={t("dismissTitle")}
        description={t("dismissBody", { title: selected?.title ?? "" })}
        size="sm"
        closeLabel={tc("close")}
        footer={
          <>
            <Button variant="ghost" onClick={closeModal}>
              {tc("cancel")}
            </Button>
            <Button variant="primary" loading={dismiss.isPending} onClick={submit}>
              {t("dismissConfirm")}
            </Button>
          </>
        }
      >
        <ReasonField
          id="ai-review-dismiss-reason"
          label={t("reasonLabel")}
          hint={t("dismissReasonHint")}
          value={reason}
          error={reasonError}
          onChange={(v) => {
            setReason(v);
            if (reasonError) setReasonError(null);
          }}
        />
      </Modal>
    </>
  );
}

const KNOWN_REASON_CODES = new Set<string>([
  "duplicate_listing",
  "misleading_content",
  "policy_violation",
  "incomplete_info",
  "spam",
  "other",
]);

/**
 * Where the "open record" link lands. The backend's `detail_url` points at a
 * per-id record route that the frontend does not yet expose, so we deep-link to
 * the correct existing moderation queue (jobs/events) for the item type instead
 * of shipping a dead link. Swap to `detail_url` once those detail routes land.
 */
function queueHref(itemType: AiReviewQueueItem["item_type"]): string {
  return itemType === "job"
    ? "/university/moderation/jobs"
    : "/university/moderation/events";
}

function ReasonField({
  id,
  label,
  hint,
  value,
  error,
  onChange,
}: {
  id: string;
  label: string;
  hint: string;
  value: string;
  error: string | null;
  onChange: (value: string) => void;
}) {
  return (
    <div>
      <label
        htmlFor={id}
        className="mb-1.5 block text-sm font-semibold text-[var(--text-primary)]"
      >
        {label}
        <span className="ml-0.5 text-[var(--brand-red)]" aria-hidden>
          *
        </span>
      </label>
      <textarea
        id={id}
        rows={3}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        aria-invalid={error ? true : undefined}
        aria-describedby={error ? `${id}-error` : undefined}
        className="w-full rounded-xl border border-[var(--border-default)] bg-white px-3.5 py-2.5 text-sm text-[var(--text-primary)] outline-none focus:border-[var(--brand-primary)]/50 focus:bg-white focus:ring-2 focus:ring-[var(--brand-primary)]/30"
      />
      {error && (
        <p id={`${id}-error`} className="mt-1 text-xs font-medium text-[var(--brand-red)]">
          {error}
        </p>
      )}
      <p className="mt-2 text-xs text-[var(--text-muted)]">{hint}</p>
    </div>
  );
}
