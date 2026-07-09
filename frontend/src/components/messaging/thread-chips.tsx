"use client";

import { useTranslations } from "next-intl";
import { CheckCircle, Clock, Prohibit, XCircle } from "@phosphor-icons/react";
import { cn } from "@/lib/utils";
import type { AssignmentState, RequestState } from "@/lib/api";

/**
 * Request-gate chip. Renders the SERVER-localized `request_label` verbatim (the
 * text is decided backend-side); this component only chooses the v9-monochrome
 * styling per state. `accepted` renders nothing — an open conversation needs no
 * chip. No amber (reserved for sponsored disclosure) or blue accents are used.
 */
export function RequestChip({
  state,
  label,
  className,
}: {
  state: RequestState;
  /** Server-rendered `request_label`. */
  label: string;
  className?: string;
}) {
  if (state === "accepted") return null;

  const Icon =
    state === "pending" ? Clock : state === "blocked" ? Prohibit : XCircle;
  const tone =
    state === "blocked"
      ? "bg-[var(--red-50)] text-[var(--brand-red)] shadow-[inset_0_0_0_1px_var(--red-200,rgba(220,38,38,0.25))]"
      : state === "declined"
        ? "bg-[var(--bg-muted)] text-[var(--text-muted)] shadow-[inset_0_0_0_1px_rgba(0,0,0,0.06)]"
        : "bg-[var(--bg-subtle)] text-[var(--text-secondary)] shadow-[inset_0_0_0_1px_rgba(0,0,0,0.08)]";

  return (
    <span
      className={cn(
        "inline-flex shrink-0 items-center gap-1 rounded-full px-1.5 py-0.5 text-[10px] font-semibold",
        tone,
        className,
      )}
    >
      <Icon aria-hidden weight="bold" className="size-3" />
      {label}
    </span>
  );
}

/**
 * Org-inbox assignment chip (unassigned / assigned / resolved). Localized here
 * (no server label exists for assignment). Green = resolved (success semantic);
 * ink-tint = assigned; neutral outline = unassigned.
 */
export function AssignmentChip({
  state,
  className,
}: {
  state: AssignmentState;
  className?: string;
}) {
  const t = useTranslations("messaging");
  const map: Record<string, { label: string; tone: string; Icon: typeof Clock }> = {
    unassigned: {
      label: t("assignmentUnassigned"),
      tone: "bg-[var(--bg-subtle)] text-[var(--text-muted)] shadow-[inset_0_0_0_1px_rgba(0,0,0,0.08)]",
      Icon: Clock,
    },
    assigned: {
      label: t("assignmentAssigned"),
      tone: "bg-[var(--text-primary)]/[0.06] text-[var(--text-primary)] shadow-[inset_0_0_0_1px_rgba(0,0,0,0.12)]",
      Icon: CheckCircle,
    },
    resolved: {
      label: t("assignmentResolved"),
      tone: "bg-[var(--color-success)]/15 text-[var(--color-success)] shadow-[inset_0_0_0_1px_var(--color-success)]",
      Icon: CheckCircle,
    },
  };
  const entry = map[state] ?? map.unassigned!;
  const { label, tone, Icon } = entry;
  return (
    <span
      className={cn(
        "inline-flex shrink-0 items-center gap-1 rounded-full px-1.5 py-0.5 text-[10px] font-semibold",
        tone,
        className,
      )}
    >
      <Icon aria-hidden weight="bold" className="size-3" />
      {label}
    </span>
  );
}
