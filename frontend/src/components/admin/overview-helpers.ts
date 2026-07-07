/**
 * Pure helpers for the Platform Overview landing screen.
 * Extracted for unit-testability — no React, no i18n, no side effects.
 */

import type { StatusTone } from "@/components/ui";

/**
 * Outbox health tone.
 * - active  (teal)  : no failures and no pending messages
 * - pending (amber) : pending messages > 0 but no failures in last hour
 * - rejected (red)  : failed_last_hour > 0
 */
export type OutboxTone = "active" | "pending" | "rejected";

/**
 * Returns the tonal classification for an outbox health state.
 *
 * @param pending - Number of outbox messages currently pending send.
 * @param failedLastHour - Number of outbox failures in the last hour.
 */
export function outboxTone(
  pending: number,
  failedLastHour: number,
): OutboxTone {
  if (!isFinite(pending) || !isFinite(failedLastHour)) return "active";
  if (failedLastHour > 0) return "rejected";
  if (pending > 0) return "pending";
  return "active";
}

/**
 * Map OutboxTone to the StatusBadge StatusTone primitive.
 */
export function outboxToneToStatusTone(tone: OutboxTone): StatusTone {
  if (tone === "active") return "active";
  if (tone === "pending") return "pending";
  return "rejected";
}
