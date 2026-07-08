/**
 * Pure presentational logic for the student "interview readiness / my progress"
 * view (WS-6). Framework-free (no React, no fetch) so the HONEST low-data
 * contract is unit-testable without a DOM (vitest env is `node`).
 *
 * Non-negotiable: below the backend's minimum evaluated answers the readiness
 * signal is `status === "not_enough_data"` with `readiness_pct === null`. The UI
 * must render an honest "practise N more time(s)" state and NEVER a fabricated
 * percentage. Nothing here derives a provider/model/token/confidence internal —
 * the only inputs are the 1-5 coaching scores already aggregated server-side.
 */
import type { InterviewReadiness } from "@/lib/api/interview-prep";

export type ReadinessTone = "ok" | "progress" | "low";

export interface ReadinessView {
  /** True when the backend has enough evaluated answers to show a real signal. */
  hasSignal: boolean;
  /** Masked readiness percentage, or null in the honest low-data state. */
  pct: number | null;
  /** Clamped 0..100 fill for a bar/ring; 0 in the low-data state. */
  fillPct: number;
  /** Band code (localized by the caller), or null in the low-data state. */
  band: InterviewReadiness["band"];
  /** Trend code (localized by the caller), or null in the low-data state. */
  trend: InterviewReadiness["trend"];
  /** Coarse tone for the band chip (green ready → amber developing). */
  tone: ReadinessTone;
  /** How many more evaluated answers are needed (only meaningful when !hasSignal). */
  answersNeeded: number;
  /** Number of practice attempts made so far. */
  attempts: number;
}

/**
 * Band → coarse tone. `interview_ready`/`progressing` read as healthy (green),
 * `emerging` as in-progress (neutral/amber-lean), `developing` as low (amber).
 * Never color-only in the UI — the band label always accompanies the chip.
 */
export function readinessBandTone(
  band: InterviewReadiness["band"],
): ReadinessTone {
  if (band === "interview_ready" || band === "progressing") return "ok";
  if (band === "emerging") return "progress";
  return "low";
}

/**
 * Derive the honest display view from the backend readiness signal. In the
 * `not_enough_data` state `pct`/`band`/`trend` stay null and `hasSignal` is
 * false, so the UI shows "practise {answersNeeded} more" instead of a number.
 */
export function interviewReadinessView(
  readiness: InterviewReadiness,
): ReadinessView {
  const hasSignal =
    readiness.status === "ready_signal" && readiness.readiness_pct !== null;
  const pct = hasSignal ? readiness.readiness_pct : null;
  return {
    hasSignal,
    pct,
    fillPct: pct === null ? 0 : Math.min(100, Math.max(0, pct)),
    band: hasSignal ? readiness.band : null,
    trend: hasSignal ? readiness.trend : null,
    tone: hasSignal ? readinessBandTone(readiness.band) : "low",
    answersNeeded: Math.max(0, readiness.answers_needed),
    attempts: Math.max(0, readiness.attempts),
  };
}
