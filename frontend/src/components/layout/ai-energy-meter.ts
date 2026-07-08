import type { Persona } from "@/stores/auth-store";
import type { AiEnergyUsage } from "@/lib/api/ai-assistant";

/**
 * Shared presentational logic for the masked "AI energy" meter.
 *
 * This is the single source of truth for turning the backend's masked
 * `AiEnergyUsage` shape (`GET /ai/usage/me`) into the small set of display
 * values the meter surfaces need — the compact header meter and the sidebar
 * usage card both derive from here so the two never drift. Deliberately masked:
 * only the remaining energy **percentage** and coarse block/warn state are
 * derived; no tokens, USD, provider, or model ever pass through this module.
 */

export type AiEnergyTone = "ok" | "warn" | "block";

/**
 * Remaining energy at/below this percentage (0..100) shows the amber "warn"
 * treatment even before the backend raises its own soft-warning flag. Mirrors
 * the "80% used → warn" threshold from the student-AI-overhaul design (WS-1):
 * 80% used == 20% remaining.
 */
export const ENERGY_WARN_REMAINING_PCT = 20;

export interface AiEnergyMeterState {
  /** Remaining weekly energy, 0..100, rounded for display. */
  pct: number;
  /** Clamped 0..100 fill fraction for a bar/ring visual. */
  fillPct: number;
  /** block > warn > ok — derived from the masked usage shape only. */
  tone: AiEnergyTone;
  /** Shared partner-org pool (`scope === "org"`) vs a personal budget. */
  isOrg: boolean;
  /** 3h rolling burst soft-cap crossed (advisory, never blocking). */
  overSoftCap: boolean;
}

/**
 * Derive the meter's display state from the masked usage payload. Priority is
 * block > warn > ok. A hard `blocked` gate always wins; otherwise the backend's
 * own `warning` flag OR a low remaining balance (`<= ENERGY_WARN_REMAINING_PCT`)
 * raises the amber warn treatment.
 */
export function deriveEnergyMeterState(u: AiEnergyUsage): AiEnergyMeterState {
  const pct = Math.round(u.energy_pct);
  const tone: AiEnergyTone = u.blocked
    ? "block"
    : u.warning || pct <= ENERGY_WARN_REMAINING_PCT
      ? "warn"
      : "ok";
  return {
    pct,
    fillPct: Math.min(100, Math.max(0, u.energy_pct)),
    tone,
    isOrg: u.scope === "org",
    overSoftCap: u.session_3h.over_soft_cap,
  };
}

/**
 * The compact header energy meter is a student-only affordance: it renders only
 * for an authenticated student. Guests, partners, and university staff never see
 * it (partner/university energy lives in their operating-shell sidebar card).
 * `null`/undefined persona on an authenticated session defaults to student,
 * matching the marketplace header's own persona fallback.
 */
export function headerEnergyMeterVisible(
  status: "unknown" | "authenticated" | "guest",
  persona: Persona | null | undefined,
): boolean {
  return status === "authenticated" && (persona ?? "student") === "student";
}
