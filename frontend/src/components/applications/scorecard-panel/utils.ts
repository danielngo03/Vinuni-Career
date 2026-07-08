import type { StatusTone } from "@/components/ui";
import type { Scorecard, ScorecardRecommendation } from "@/lib/api";

export const SCORE_VALUES = [1, 2, 3, 4, 5] as const;

/** Recommendation → badge tone. Color is always paired with the text label. */
export const RECOMMENDATION_TONE: Record<ScorecardRecommendation, StatusTone> = {
  strong_yes: "accepted",
  yes: "active",
  no: "pending",
  strong_no: "rejected",
};

export type ScoreMap = Record<string, number>;

export function minesScoreMap(mine: Scorecard | null): ScoreMap {
  const out: ScoreMap = {};
  if (!mine) return out;
  for (const s of mine.scores) {
    if (typeof s.score === "number") out[s.criterion_key] = s.score;
  }
  return out;
}
