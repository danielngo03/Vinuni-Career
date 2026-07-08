"use client";

import { useTranslations } from "next-intl";
import { Clock, UserCheck } from "@phosphor-icons/react";
import { StatusBadge, Select } from "@/components/ui";
import { cn } from "@/lib/utils";
import { MODERATION_REASON_CODES, type ModerationReasonCode } from "@/lib/api";

/**
 * SLA / queue-age badge (jobs/events/advertising moderation). Overdue uses the
 * `rejected` (red-adjacent) tone deliberately — a genuine, non-decorative alert
 * — everything else stays the quiet `pending` amber tone.
 */
export function SlaBadge({
  dueBy,
  ageHours,
  isOverdue,
}: {
  dueBy?: string | null;
  ageHours?: number | null;
  isOverdue?: boolean;
}) {
  const t = useTranslations("common");
  if (dueBy == null && ageHours == null) return null;
  const label = isOverdue
    ? t("moderationQueue.slaOverdue", { hours: Math.round(ageHours ?? 0) })
    : t("moderationQueue.slaAge", { hours: Math.round(ageHours ?? 0) });
  return (
    <StatusBadge tone={isOverdue ? "rejected" : "pending"}>
      <Clock aria-hidden weight="bold" className="size-3" />
      {label}
    </StatusBadge>
  );
}

/** Claim/assignee indicator — quiet when unclaimed, informative once claimed. */
export function ClaimBadge({
  claimedBy,
  isMine,
}: {
  claimedBy?: string | null;
  isMine: boolean;
}) {
  const t = useTranslations("common");
  if (!claimedBy) return null;
  return (
    <StatusBadge tone="info">
      <UserCheck aria-hidden weight="bold" className="size-3" />
      {isMine ? t("moderationQueue.claimedByMe") : t("moderationQueue.claimedByOther")}
    </StatusBadge>
  );
}

/**
 * Structured reason-code select shared by job/event/placement reject + escalate
 * dialogs. The free-text note ("Other" requires a note) is the existing
 * required `reason`/note textarea already present in each dialog — this only
 * adds the structured code alongside it.
 */
export function ReasonCodeSelect({
  id,
  value,
  onChange,
  error,
  required,
}: {
  id: string;
  value: ModerationReasonCode | string;
  onChange: (value: ModerationReasonCode | string) => void;
  error?: string | null;
  required?: boolean;
}) {
  const t = useTranslations("common");
  return (
    <Select
      id={id}
      label={t("moderationQueue.reasonCodeLabel")}
      required={required}
      value={value}
      error={error ?? undefined}
      onChange={(e) => onChange(e.target.value)}
      options={MODERATION_REASON_CODES.map((code) => ({
        value: code,
        label: t(`moderationQueue.reasonCodes.${code}`),
      }))}
    />
  );
}

/** Row-level checkbox for multi-select tables (stable size, keyboard/focus-visible). */
export function RowSelectCheckbox({
  checked,
  onChange,
  label,
}: {
  checked: boolean;
  onChange: (checked: boolean) => void;
  label: string;
}) {
  return (
    <input
      type="checkbox"
      checked={checked}
      onChange={(e) => onChange(e.target.checked)}
      onClick={(e) => e.stopPropagation()}
      aria-label={label}
      className={cn(
        "size-4 cursor-pointer rounded border-[var(--border-default)]",
        "accent-[var(--brand-primary)] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--brand-primary)]",
      )}
    />
  );
}

export interface BulkResultRow {
  id: string;
  success: boolean;
  message?: string;
}

/** Per-item partial-success/failure list after a bulk approve/reject call. */
export function BulkResultList({
  results,
  getLabel,
}: {
  results: BulkResultRow[];
  getLabel: (id: string) => string;
}) {
  const t = useTranslations("common");
  const failed = results.filter((r) => !r.success);
  const succeeded = results.filter((r) => r.success);
  return (
    <div className="space-y-3">
      <p className="text-sm font-semibold text-[var(--text-primary)]">
        {t("moderationQueue.bulkResultSummary", {
          success: succeeded.length,
          failed: failed.length,
        })}
      </p>
      {failed.length > 0 && (
        <ul className="space-y-1.5 rounded-xl border border-[var(--red-400)]/40 bg-[var(--red-50)] p-3">
          {failed.map((r) => (
            <li key={r.id} className="text-xs text-[var(--brand-red)]">
              <span className="font-semibold">{getLabel(r.id)}</span>
              {r.message ? `: ${r.message}` : ""}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
