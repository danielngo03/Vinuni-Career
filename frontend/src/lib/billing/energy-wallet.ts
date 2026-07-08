/**
 * Pure presentational logic for the student "AI energy wallet" panel on
 * `/student/billing`. Framework-free so the MASKED contract is unit-testable
 * without a DOM (vitest env is `node`).
 *
 * Masking is the whole point: the panel surfaces only the remaining weekly
 * energy PERCENTAGE, a coarse wallet BUCKET, and the ok/warn/block tone. It
 * never derives (or lets a caller render) a raw wallet credit count, token
 * count, USD figure, or any provider/model signal — those never leave this
 * module. Reuses the same `deriveEnergyMeterState` derivation as the header and
 * sidebar meters so the numbers never drift.
 */
import type { AiEnergyUsage } from "@/lib/api/ai-assistant";
import {
  deriveEnergyMeterState,
  type AiEnergyTone,
} from "@/components/layout/ai-energy-meter";

/** Coarse wallet state — deliberately NOT a number. */
export type WalletBucket = "none" | "reserve";

export interface EnergyWalletView {
  /** Remaining weekly energy %, 0..100 (rounded). */
  pct: number;
  /** Clamped 0..100 fill fraction for the bar. */
  fillPct: number;
  /** ok / warn / block — reused from the shared meter derivation. */
  tone: AiEnergyTone;
  /** Weekly energy exhausted — new AI actions are refused. */
  blocked: boolean;
  /** Backend soft-warning (nearing limit / burst / already-exceeded). */
  warning: boolean;
  /** Shared partner-org pool vs a personal budget. */
  isOrg: boolean;
  /** Coarse top-up reserve state — never a raw credit count. */
  walletBucket: WalletBucket;
}

/**
 * Coarse wallet bucket from the opaque top-up reserve. Returns a two-state
 * enum only: `reserve` when the student has any purchased top-up energy left,
 * `none` otherwise. The exact credit count is intentionally not exposed.
 */
export function deriveWalletBucket(usage: AiEnergyUsage): WalletBucket {
  return usage.weekly.wallet > 0 ? "reserve" : "none";
}

/**
 * Derive the masked wallet-panel view from the usage payload. Everything here
 * is display-safe: a percentage, coarse tone/flags, and a wallet bucket enum.
 */
export function energyWalletView(usage: AiEnergyUsage): EnergyWalletView {
  const { pct, fillPct, tone, isOrg } = deriveEnergyMeterState(usage);
  return {
    pct,
    fillPct,
    tone,
    blocked: usage.blocked === true,
    warning: usage.warning === true,
    isOrg,
    walletBucket: deriveWalletBucket(usage),
  };
}
