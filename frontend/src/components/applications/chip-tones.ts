import type { ChipTone } from "@/components/kit";

/**
 * v10 StatusChip tone maps for the partner recruiter workspace. Color is a
 * data-viz signal that is ALWAYS paired with a text label (the chip children),
 * never the sole signal. Semantic tones for lifecycle state; categorical hues
 * only where a genuine category needs distinguishing (e.g. a sent offer).
 */
export const APPLICATION_STATUS_CHIP: Record<string, ChipTone> = {
  submitted: "info",
  under_review: "warning",
  rejected: "danger",
  withdrawn: "neutral",
  // v10 reserves emerald/green for verified/success/positive-terminal states.
  hired: "success",
};

export const REVEAL_STATUS_CHIP: Record<string, ChipTone> = {
  none: "neutral",
  pending: "warning",
  accepted: "success",
  declined: "danger",
  expired: "neutral",
};

export const INTERVIEW_STATUS_CHIP: Record<string, ChipTone> = {
  scheduled: "info",
  completed: "success",
  cancelled: "neutral",
  no_show: "danger",
  rescheduled: "warning",
};

export const OFFER_STATUS_CHIP: Record<string, ChipTone> = {
  draft: "neutral",
  pending_approval: "warning",
  approved: "info",
  sent: "violet",
  accepted: "success",
  declined: "danger",
  expired: "neutral",
  rescinded: "neutral",
};

export const RECOMMENDATION_CHIP: Record<string, ChipTone> = {
  strong_yes: "success",
  yes: "teal",
  no: "amber",
  strong_no: "danger",
};

/** Two-letter initials for an avatar fallback. Handles UV-xxxx handles too. */
export function initials(name: string): string {
  const trimmed = name.trim();
  if (!trimmed) return "?";
  const parts = trimmed.split(/[\s-]+/).filter(Boolean);
  if (parts.length === 1) return parts[0]!.slice(0, 2).toUpperCase();
  return (parts[0]![0]! + parts[parts.length - 1]![0]!).toUpperCase();
}
