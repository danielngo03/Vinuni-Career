import type { PipelineCard } from "@/lib/api";
import type { ChipTone } from "@/components/kit";

/** The synthetic droppable id for the pre-pipeline "new" bucket (stage_id null). */
export const NEW_COLUMN_ID = "__new__";

/** Application lifecycle status → soft StatusChip tone (color = meaning). */
export const APPLICATION_CHIP_TONE: Record<string, ChipTone> = {
  submitted: "sky",
  under_review: "amber",
  rejected: "danger",
  withdrawn: "neutral",
  hired: "success",
};

/** Offer status → soft StatusChip tone. Falls back to neutral for unknowns. */
export const OFFER_CHIP_TONE: Record<string, ChipTone> = {
  draft: "neutral",
  pending_approval: "amber",
  approved: "amber",
  sent: "sky",
  accepted: "success",
  declined: "danger",
  withdrawn: "neutral",
  expired: "neutral",
};

/** A card is flagged "stale" once it has sat in a column past this threshold. */
export const STALE_DAYS = 7;

/** Minimum rollback-reason length required by the backend (ADR-0005 §5). */
export const MIN_REASON = 20;

/** Whole days a card has sat in its current stage, or null when it has no
 *  stage row yet (the "new" pre-pipeline bucket has a null `entered_at`). */
export function daysInStage(enteredAt: string | null | undefined): number | null {
  if (!enteredAt) return null;
  const t = new Date(enteredAt).getTime();
  if (Number.isNaN(t)) return null;
  return Math.floor((Date.now() - t) / 86_400_000);
}

/** The candidate's display name (identity is always present on the card). */
export function cardHandle(card: PipelineCard): string {
  return card.applicant.full_name || "—";
}
