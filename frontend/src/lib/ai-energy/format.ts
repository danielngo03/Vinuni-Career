import type { StatusTone } from "@/components/ui";
import type { AiEnergyTopupStatus } from "@/lib/api";

/**
 * Pure helpers for the AI energy surfaces (admin allocation panel + member
 * top-up dialog). No React, no i18n — safe to unit test. Energy values are
 * opaque product credits, never tokens/USD/provider units.
 */

export type EnergyTone = "critical" | "warning" | "normal";

/**
 * Meter tone from a pool/snapshot state. `blocked` wins over `warning`; a plain
 * pool with neither flag is `normal`. Drives the ink/amber/red bar colour.
 */
export function energyTone(state: {
  blocked?: boolean | null;
  warning?: boolean | null;
}): EnergyTone {
  if (state.blocked) return "critical";
  if (state.warning) return "warning";
  return "normal";
}

/** Clamp a raw remaining-energy percentage to a safe 0..100 meter width. */
export function clampPct(pct: number | null | undefined): number {
  if (pct == null || Number.isNaN(pct)) return 0;
  return Math.min(100, Math.max(0, pct));
}

/** Top-up status → StatusBadge tone (colour is never the only signal). */
export const TOPUP_STATUS_TONE: Record<AiEnergyTopupStatus, StatusTone> = {
  pending: "pending",
  paid: "active",
  cancelled: "rejected",
};

/**
 * Locale-aware whole-number formatting for opaque energy credits (e.g. a pack of
 * `1200` renders as `1,200` / `1.200`). Never a currency — packs carry a
 * separate VND `price_amount`.
 */
export function formatUnits(
  units: number | null | undefined,
  locale: string,
): string {
  if (units == null || Number.isNaN(units)) return "—";
  return new Intl.NumberFormat(locale === "vi" ? "vi-VN" : "en-US", {
    maximumFractionDigits: 0,
  }).format(units);
}
