import { api } from "../client";

/* -------------------------- Scorecards (ADR-0005) ------------------------- */
/*
 * Scorecards are PARTNER-INTERNAL evaluations. They never appear on any
 * student-facing projection, notification, or email (ADR-0005 §2/§4). All three
 * calls below are org-scoped: a cross-org / non-partner caller gets a 404.
 */

/** The 4 fixed V1 criteria keys (ADR-0005 §1). Display order. */
export type ScorecardCriterionKey =
  | "technical"
  | "communication"
  | "culture_fit"
  | "motivation";

export const SCORECARD_CRITERIA: readonly ScorecardCriterionKey[] = [
  "technical",
  "communication",
  "culture_fit",
  "motivation",
];

/** The primary advance signal — a required 4-value enum (ADR-0005 §1). */
export type ScorecardRecommendation =
  | "strong_yes"
  | "yes"
  | "no"
  | "strong_no";

/** Picker order: most positive → most negative. */
export const SCORECARD_RECOMMENDATIONS: readonly ScorecardRecommendation[] = [
  "strong_yes",
  "yes",
  "no",
  "strong_no",
];

/** One criterion score on submit (`score` is an integer 1..5). */
export interface ScorecardScoreInput {
  criterion_key: ScorecardCriterionKey | string;
  score: number;
}

/** Submit / upsert body for the caller's scorecard on the current ACTIVE stage. */
export interface SubmitScorecardBody {
  scores: ScorecardScoreInput[];
  recommendation: ScorecardRecommendation;
  comment?: string | null;
  /** Per-scorecard optimistic version on edit; a stale value yields a 409. */
  version?: number;
}

/** One scored criterion as returned by the presenter (carries its label). */
export interface ScorecardScore {
  criterion_key: string;
  label: string;
  score: number | null;
}

/**
 * One reviewer's scorecard. `reviewer_id` is a PARTNER-ORG member id, never the
 * student — there is no student-identity field on a scorecard (ADR-0005 §4).
 */
export interface Scorecard {
  id: string;
  stage_id: string;
  reviewer_id: string;
  /** True when this is the caller's own scorecard. */
  is_mine: boolean;
  recommendation: ScorecardRecommendation | string;
  recommendation_label: string | null;
  /** Derived mean of the criterion scores (1.0–5.0), or null. */
  overall_score: number | null;
  scores: ScorecardScore[];
  comment: string | null;
  status: "submitted" | "withdrawn" | string;
  version: number;
  submitted_at: string | null;
  updated_at: string | null;
}

/**
 * Stage aggregate over SUBMITTED scorecards. ANCHORING (ADR-0005 §2): the
 * score-derived fields (`avg_overall`, `recommendation_summary`, `by_criterion`)
 * are withheld — `null` / `{}` — until the caller has submitted their OWN
 * scorecard for the stage. Only the round counters are exposed pre-submit, so a
 * reviewer can never be anchored by peers' scores.
 */
export interface ScorecardAggregate {
  submitted_count: number;
  required: number;
  gate_met: boolean;
  avg_overall: number | null;
  recommendation_summary: Record<string, number>;
  by_criterion: Record<string, number>;
}

/** A criterion label pair for building the submit form. */
export interface ScorecardCriterionMeta {
  criterion_key: string;
  label: string;
}

/**
 * Anchoring-aware list response (also returned by submit + withdraw).
 *
 * - `stage_id` is null when the candidate is not in a review stage yet
 *   (pre-pipeline) — scorecards do not apply.
 * - `mine` is the caller's own scorecard, or null before they submit.
 * - `scorecards` (OTHER reviewers') is EMPTY until the caller submits their own.
 * - `aggregate` score fields are likewise withheld until then.
 */
export interface ScorecardListResult {
  stage_id: string | null;
  mine: Scorecard | null;
  scorecards: Scorecard[];
  aggregate: ScorecardAggregate;
  criteria: ScorecardCriterionMeta[];
}

/** Request body for AI scorecard suggestion. */
export interface ScorecardAiSuggestBody {
  notes: string;
  job_title?: string;
  interview_stage?: string;
}

/** Per-criterion suggestion from the AI scorecard assistant. */
export interface ScorecardAiCriterionSuggestion {
  score: number | null;
  reasoning: string;
}

/** AI screening brief — advisory-only candidate summary for partners (GET). */
export interface ScreeningBrief {
  bullets: string[];
  suitability: "strong" | "moderate" | "weak" | null;
  is_fallback: boolean;
  prompt_version: number;
}

/** Full AI scorecard suggestion response (human_review tier). */
export interface ScorecardAiSuggestion {
  criteria: Record<ScorecardCriterionKey, ScorecardAiCriterionSuggestion>;
  recommendation: ScorecardRecommendation | null;
  overall_reasoning: string;
  confidence: "high" | "medium" | "low";
  prompt_version: number;
  is_fallback: boolean;
}

/* --------------------------------- Calls ---------------------------------- */

export const scorecardsApi = {
  /**
   * Partner: submit / upsert the caller's scorecard for the candidate's current
   * ACTIVE stage. 422 on a missing/invalid criterion or recommendation; 409 if
   * the application is not actively under review or `version` is stale; 404
   * cross-org. Returns the anchoring-aware stage view (the caller has now
   * submitted, so the aggregate + other reviewers are revealed).
   */
  submitScorecard(
    id: string,
    body: SubmitScorecardBody,
  ): Promise<ScorecardListResult> {
    return api.post<ScorecardListResult>(`/applications/${id}/scorecards`, body);
  },

  /**
   * Partner: list scorecards for a stage (defaults to the current ACTIVE stage).
   * ANCHORING: before the caller submits their own, only the round counters are
   * returned (`mine: null`, `scorecards: []`, aggregate score fields withheld);
   * after submitting, `mine` + the full list + aggregate are revealed.
   */
  listScorecards(
    id: string,
    stageId?: string | null,
  ): Promise<ScorecardListResult> {
    return api.get<ScorecardListResult>(`/applications/${id}/scorecards`, {
      query: { stage_id: stageId ?? undefined },
    });
  },

  /**
   * Partner: soft-withdraw the caller's OWN scorecard (author-only; another
   * reviewer's id or a missing one is a 404). Excluded from the gate + aggregate.
   * Returns the refreshed stage view.
   */
  withdrawScorecard(
    id: string,
    scorecardId: string,
  ): Promise<ScorecardListResult> {
    return api.post<ScorecardListResult>(
      `/applications/${id}/scorecards/${scorecardId}/withdraw`,
      {},
    );
  },

  /**
   * Partner: AI-suggested criterion scores from free-text interview notes.
   * human_review tier — output is a DRAFT; partner must review before submitting.
   */
  aiScorecardSuggest(
    id: string,
    body: ScorecardAiSuggestBody,
  ): Promise<ScorecardAiSuggestion> {
    return api.post<ScorecardAiSuggestion>(
      `/applications/${id}/ai-scorecard-suggest`,
      body,
    );
  },

  /** Partner: AI screening brief comparing the candidate CV to the job role. */
  getScreeningBrief(id: string): Promise<ScreeningBrief> {
    return api.get<ScreeningBrief>(`/applications/${id}/ai-screening-brief`);
  },
};
