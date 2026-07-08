/**
 * Pure presentational + gating logic for the student job-detail intelligence
 * surface (WS-4 / WS-14 / WS-15).
 *
 * Kept framework-free (no React, no fetch) so the on-demand behaviour that the
 * drawers depend on — the guest gate, the "fire the model call ONLY when the
 * drawer opens" rule, and the honest competition-band rendering — is unit
 * testable without a DOM (the repo's vitest environment is `node`).
 *
 * Privacy: nothing here ever derives a raw applicant count, an individual score,
 * an exact rank, or any provider/model/token internal. Competition inputs are
 * coarse bands only; "unknown"/"low_signal" render as an honest "not enough
 * data" state, never a fabricated value.
 */
import type { Persona } from "@/stores/auth-store";
import type { AiEnergyUsage } from "@/lib/api/ai-assistant";
import type {
  StudentApplyReadiness,
  StudentCompetitionIntelligence,
  StudentJobFit,
} from "@/lib/api/jobs";
import {
  deriveEnergyMeterState,
  type AiEnergyTone,
} from "@/components/layout/ai-energy-meter";

export type AuthStatus = "unknown" | "authenticated" | "guest";

/**
 * Personalized fit + competition are owner-scoped (the student's own CVs) and
 * login-only. Guests and non-student personas must never see either surface
 * (they get the public, non-personalized job detail instead).
 */
export function isStudentViewer(
  status: AuthStatus,
  persona: Persona | null | undefined,
): boolean {
  return status === "authenticated" && persona === "student";
}

/**
 * The on-demand drawers each fire a model-metered call (fit-explanation /
 * competition-explanation) that must run ONLY when the drawer is open — never on
 * the default score-only job-detail load. This is the exact `enabled` flag the
 * drawer's React Query uses, so a closed drawer provably fetches nothing.
 */
export function drawerQueryEnabled(open: boolean): boolean {
  return open === true;
}

/* -------------------------------------------------------------------------- */
/* CV strength / apply-readiness (WS-15) — derived, no new endpoint            */
/* -------------------------------------------------------------------------- */

export type CvReadinessLevel =
  | "no_cv"
  | "applied"
  | "closed"
  | "ready"
  | "almost"
  | "needs_work";

export interface CvReadiness {
  level: CvReadinessLevel;
  /** Overall CV strength 0..100 (the deterministic fit score) or null (no CV). */
  score: number | null;
  /** Whether the student can still act (apply) on this job right now. */
  actionable: boolean;
  stale: boolean;
}

/**
 * Compact CV strength + apply-readiness for the default panel. Purely derived
 * from the already-fetched deterministic fit score/bands + apply readiness — no
 * extra request, no AI, no fabrication. Terminal states (already applied,
 * deadline passed, no CV) win over the raw score band.
 */
export function deriveCvReadiness(
  fit: StudentJobFit,
  applyReadiness: StudentApplyReadiness,
): CvReadiness {
  const stale = fit.stale === true;
  if (!applyReadiness.has_active_cv || fit.status === "no_active_cv") {
    return { level: "no_cv", score: null, actionable: false, stale: false };
  }
  const score = fit.score;
  if (applyReadiness.already_applied) {
    return { level: "applied", score, actionable: false, stale };
  }
  if (applyReadiness.deadline_passed) {
    return { level: "closed", score, actionable: false, stale };
  }
  // Active, applyable CV: grade strength off the deterministic score. A stale CV
  // never reads as fully "ready" even at a high score.
  let level: CvReadinessLevel;
  if (score !== null && score >= 80 && !stale) level = "ready";
  else if (score !== null && score >= 50) level = "almost";
  else level = "needs_work";
  return { level, score, actionable: applyReadiness.ready, stale };
}

/* -------------------------------------------------------------------------- */
/* Competition — honest band rendering (WS-5)                                  */
/* -------------------------------------------------------------------------- */

/** The coarse "unknown"/"low_signal" sentinels the backend uses for a thin pool. */
const UNKNOWN_BAND = new Set(["unknown", "low_signal"]);

export function isKnownBand(value: string | null | undefined): boolean {
  return value != null && !UNKNOWN_BAND.has(value);
}

/**
 * Is there ANY real competition signal to show? False when the pool is below the
 * min threshold (`signal === "low_signal"`) or no label was produced — the UI
 * then renders the honest "not enough data yet" state instead of empty bands.
 */
export function hasCompetitionSignal(
  competition: StudentCompetitionIntelligence,
): boolean {
  return competition.signal !== "low_signal" && competition.label != null;
}

export type CompetitionRowKey =
  | "applicants_per_seat"
  | "strong_density"
  | "standing_vs_strong"
  | "applicant_quality"
  | "deadline";

export interface CompetitionRow {
  key: CompetitionRowKey;
  /** The raw band value (already known-guarded). */
  value: string;
}

/**
 * The band rows to render in the Competition drawer dashboard, in priority
 * order, with every "unknown"/"low_signal" band dropped so we never render a
 * meaningless or fabricated row. `deadline` is always shown (it is always known,
 * including `no_deadline`). Never emits a raw count — bands only.
 */
export function competitionRows(
  competition: StudentCompetitionIntelligence,
): CompetitionRow[] {
  const rows: CompetitionRow[] = [];
  if (isKnownBand(competition.applicants_per_seat_band)) {
    rows.push({
      key: "applicants_per_seat",
      value: competition.applicants_per_seat_band,
    });
  }
  if (isKnownBand(competition.strong_competitor_density)) {
    rows.push({
      key: "strong_density",
      value: competition.strong_competitor_density,
    });
  }
  if (isKnownBand(competition.standing_vs_strong)) {
    rows.push({
      key: "standing_vs_strong",
      value: competition.standing_vs_strong,
    });
  }
  if (isKnownBand(competition.applicant_quality_bucket)) {
    rows.push({
      key: "applicant_quality",
      value: competition.applicant_quality_bucket,
    });
  }
  // Deadline pressure is always meaningful (no_deadline included).
  rows.push({ key: "deadline", value: competition.deadline_freshness });
  return rows;
}

/** Coarse tone for a competition level label (green calm → red pressure). */
export function competitionTone(
  label: StudentCompetitionIntelligence["label"],
): "low" | "moderate" | "high" {
  if (label === "low") return "low";
  if (label === "moderate") return "moderate";
  return "high"; // high / very_high
}

/* -------------------------------------------------------------------------- */
/* Energy gate (masked % only — never tokens/USD)                             */
/* -------------------------------------------------------------------------- */

export interface EnergyGate {
  /** Remaining weekly energy %, 0..100. */
  pct: number;
  tone: AiEnergyTone;
  /** Weekly energy exhausted — an AI action would be refused/degraded. */
  blocked: boolean;
}

/**
 * Masked energy state for the point-of-action cost hint shown before an AI
 * analysis runs. Reuses the exact header/sidebar derivation so the numbers never
 * drift, and exposes ONLY the remaining percentage + coarse tone — never a
 * token, USD, provider, or model value. Returns null when usage hasn't loaded.
 */
export function energyGate(usage: AiEnergyUsage | undefined): EnergyGate | null {
  if (!usage) return null;
  const { pct, tone } = deriveEnergyMeterState(usage);
  return { pct, tone, blocked: usage.blocked === true };
}

/* -------------------------------------------------------------------------- */
/* Apply CTA state (WS-15) — honest already-applied / closed disable           */
/* -------------------------------------------------------------------------- */

/**
 * Which label + enabled state the job-detail Apply button shows. Terminal
 * server-guard states (already applied, deadline passed) win over the plain
 * "apply" state so the primary CTA never invites a duplicate application that
 * the backend would reject with a `409 duplicate_application`.
 */
export type ApplyCtaLabel =
  | "loading"
  | "signIn"
  | "studentsOnly"
  | "alreadyApplied"
  | "deadlinePassed"
  | "apply";

export interface ApplyCtaState {
  label: ApplyCtaLabel;
  disabled: boolean;
  /** Show the "view my applications" link (already-applied only). */
  showViewApplications: boolean;
}

/**
 * Derive the Apply button state. `applyReadiness` is the same server guard the
 * apply endpoint enforces (`already_applied` / `deadline_passed`); when it is
 * not yet loaded (guest, still fetching) we fall back to the auth-based label.
 * Priority: hydrating > guest > non-student > already-applied > deadline-passed
 * > apply.
 */
export function deriveApplyCta(opts: {
  isHydrating: boolean;
  isGuest: boolean;
  canApply: boolean;
  alreadyApplied: boolean;
  deadlinePassed: boolean;
}): ApplyCtaState {
  const { isHydrating, isGuest, canApply, alreadyApplied, deadlinePassed } = opts;
  if (isHydrating) return { label: "loading", disabled: true, showViewApplications: false };
  if (isGuest) return { label: "signIn", disabled: false, showViewApplications: false };
  if (!canApply) return { label: "studentsOnly", disabled: true, showViewApplications: false };
  if (alreadyApplied) return { label: "alreadyApplied", disabled: true, showViewApplications: true };
  if (deadlinePassed) return { label: "deadlinePassed", disabled: true, showViewApplications: false };
  return { label: "apply", disabled: false, showViewApplications: false };
}

/**
 * Stable idempotency key for applying one improvement hand-off, so a retried
 * "Apply" click de-dupes to the same pending suggestion instead of stacking.
 */
export function improvementIdempotencyKey(cvId: string, skill: string): string {
  const slug = skill
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 48);
  return `job-fit-improve:${cvId}:${slug}`;
}
