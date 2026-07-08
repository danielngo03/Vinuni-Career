/**
 * Pure logic for the student offer-comparison + negotiation-guidance surface
 * (WS-15). Framework-free so the CONFIRMATION-GATE contract is unit-testable
 * without a DOM (vitest env is `node`).
 *
 * The negotiation call is a metered AI write action: the network request must
 * fire ONLY after the student has explicitly confirmed. `negotiationPhase`
 * models the flow and `shouldRunNegotiation` is the single predicate the
 * component uses to decide whether to fetch — a closed/idle/confirming panel
 * provably fetches nothing.
 */
import type { OfferBenchmark } from "@/lib/api/applications/offers";

/**
 * idle       — panel open, nothing requested yet (NO fetch).
 * confirming — the confirmation card is shown; awaiting explicit consent (NO fetch).
 * running    — consent given; the metered request is in flight (fetch fires here).
 * done       — a result (guidance or deterministic tips) is shown.
 * error      — the request failed; the student may retry.
 */
export type NegotiationPhase =
  | "idle"
  | "confirming"
  | "running"
  | "done"
  | "error";

/**
 * The metered negotiation request may fire only once the student has confirmed.
 * This is the exact gate the component uses, so "no fetch before confirm" is a
 * provable, tested contract: it is true iff `confirmed === true`.
 */
export function shouldRunNegotiation(confirmed: boolean): boolean {
  return confirmed === true;
}

/** Coarse tone for a `position_vs_market` verdict (never a guaranteed outcome). */
export type MarketTone = "below" | "within" | "above" | "unknown";

/**
 * Map the benchmark verdict to a coarse tone for the market-position chip.
 * `below_market` reads as attention (amber — room to negotiate), `within`/`above`
 * as neutral/positive. Unknown/undisclosed → `unknown` (no claim). This is
 * advisory framing only; the disclaimer always states no outcome is guaranteed.
 */
export function marketPositionTone(
  benchmark: OfferBenchmark | null | undefined,
): MarketTone {
  if (!benchmark || !benchmark.found || !benchmark.position_vs_market) {
    return "unknown";
  }
  switch (benchmark.position_vs_market) {
    case "below_market":
      return "below";
    case "within_market":
      return "within";
    case "above_market":
      return "above";
    default:
      return "unknown";
  }
}
