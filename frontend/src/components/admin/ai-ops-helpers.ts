/**
 * Pure helpers for the AI Operations overview screen.
 * Extracted for unit-testability — no React, no i18n, no side effects.
 */

/**
 * Budget-burn tone.
 * - teal  : burn < 70%   (healthy)
 * - amber : burn 70–90%  (approaching limit)
 * - red   : burn > 90%   (over/near-limit)
 */
export type BudgetTone = "teal" | "amber" | "red";

/**
 * Returns the tonal classification for a spend/budget ratio.
 *
 * @param spendUsd - Actual spend as a decimal USD string (or parsed number).
 * @param budgetUsd - Budget cap as a decimal USD string (or parsed number).
 * @returns "teal" | "amber" | "red"
 */
export function budgetTone(
  spendUsd: string | number,
  budgetUsd: string | number,
): BudgetTone {
  const spend = typeof spendUsd === "string" ? parseFloat(spendUsd) : spendUsd;
  const budget =
    typeof budgetUsd === "string" ? parseFloat(budgetUsd) : budgetUsd;

  if (!isFinite(spend) || !isFinite(budget) || budget <= 0) return "teal";
  const pct = (spend / budget) * 100;
  if (pct > 90) return "red";
  if (pct >= 70) return "amber";
  return "teal";
}

/**
 * Compute burn percentage (0–∞), capped display at 999 for display safety.
 */
export function budgetBurnPct(
  spendUsd: string | number,
  budgetUsd: string | number,
): number {
  const spend = typeof spendUsd === "string" ? parseFloat(spendUsd) : spendUsd;
  const budget =
    typeof budgetUsd === "string" ? parseFloat(budgetUsd) : budgetUsd;
  if (!isFinite(spend) || !isFinite(budget) || budget <= 0) return 0;
  return Math.min(Math.round((spend / budget) * 100), 999);
}

/**
 * Format a USD amount for display.
 * Keeps 4 decimal places for very small amounts (< $0.01), otherwise 2.
 */
export function formatUsd(raw: string | number): string {
  const val = typeof raw === "string" ? parseFloat(raw) : raw;
  if (!isFinite(val)) return "$—";
  if (Math.abs(val) > 0 && Math.abs(val) < 0.01) {
    return `$${val.toFixed(4)}`;
  }
  return `$${val.toFixed(2)}`;
}

/**
 * Format latency in ms → human-readable.
 * < 1000ms → "Xms", >= 1000ms → "X.Xs"
 */
export function formatLatency(ms: number): string {
  if (!isFinite(ms) || ms < 0) return "—";
  if (ms < 1000) return `${Math.round(ms)}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

/**
 * Format error rate (0–1 float) as a percentage string.
 */
export function formatErrorRate(rate: number): string {
  if (!isFinite(rate)) return "—";
  const pct = rate * 100;
  if (pct < 0.01 && pct > 0) return "<0.01%";
  return `${pct.toFixed(2)}%`;
}
