import type { PipelineCard } from "@/lib/api";

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

/** Anonymity-safe display handle. Prefers the revealed name, else UV-xxxx. */
export function cardHandle(card: PipelineCard): string {
  if (card.is_anonymous && card.applicant.anonymous_id) {
    return card.applicant.anonymous_id;
  }
  return card.applicant.display_name ?? card.applicant.anonymous_id ?? "—";
}
