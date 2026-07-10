"use client";

import type { ChipTone } from "@/components/kit";

/**
 * Partner candidate CV–JD FIT gauge scale.
 *
 * The LOCKED 3-band, colorblind-safe scale (owner decision 2026-07-07 removed
 * the blue "medium" tier). Colour is derived PURELY from the numeric product
 * fit score (0–100) — it is a deterministic CV–JD match, never an AI confidence
 * rating and never decorative. There is deliberately NO violet/indigo band here.
 *
 *   strong (>= 80) → --fit-strong (emerald)   "ready"
 *   mid    (50–79) → --fit-mid    (amber)      "usable, with gaps"
 *   weak   (<  50) → --fit-weak   (rose)       "weak signal"
 *
 * The same score→colour mapping drives the list-column ring and the drawer-
 * header ring so they can never diverge. Ring copy is always "CV–JD fit".
 */
export type MatchBand = "strong" | "mid" | "weak";

export type MatchTierKey = "matchTierStrong" | "matchTierMid" | "matchTierWeak";

interface BandDef {
  /** Semantic StatusChip tone (soft-tinted pill), paired with the tier label. */
  tone: ChipTone;
  /** Saturated ring-stroke / score-number colour token. */
  color: string;
  /** i18n tier-label key (candidates.*). */
  key: MatchTierKey;
}

const BANDS: Record<MatchBand, BandDef> = {
  strong: { tone: "success", color: "var(--fit-strong)", key: "matchTierStrong" },
  mid: { tone: "warning", color: "var(--fit-mid)", key: "matchTierMid" },
  weak: { tone: "danger", color: "var(--fit-weak)", key: "matchTierWeak" },
};

/** Score → band. Single source of truth for the whole match UI. */
export function matchBand(score: number): MatchBand {
  if (score >= 80) return "strong";
  if (score >= 50) return "mid";
  return "weak";
}

/** Semantic StatusChip tone for a score (emerald/amber/rose). */
export function matchTone(score: number): ChipTone {
  return BANDS[matchBand(score)].tone;
}

/** i18n tier-label key for a score, for the chip beside the ring. */
export function matchTierKey(score: number): MatchTierKey {
  return BANDS[matchBand(score)].key;
}

/** Saturated ring/number colour token for a score. */
export function matchColor(score: number): string {
  return BANDS[matchBand(score)].color;
}

/**
 * MatchRing — compact CV↔JD fit gauge. A colorblind-safe ring (emerald/amber/
 * rose bands driven purely by the numeric PRODUCT score — never an AI confidence
 * rating) with the score in the centre. Renders instantly from the list/detail
 * `fit.score`, and renders a neutral dashed placeholder when there is no score
 * so a column never fabricates a value.
 */
export function MatchRing({
  score,
  size = 34,
  strokeWidth = 3,
  ariaLabel,
}: {
  /** 0–100 product fit score, or `null`/`undefined` when not scored. */
  score: number | null | undefined;
  size?: number;
  strokeWidth?: number;
  ariaLabel?: string;
}) {
  if (score == null || Number.isNaN(score)) {
    return (
      <span
        aria-hidden
        className="inline-flex items-center justify-center rounded-full border border-dashed border-border text-muted-foreground"
        style={{ width: size, height: size, fontSize: Math.round(size * 0.34) }}
      >
        –
      </span>
    );
  }
  const clamped = Math.max(0, Math.min(100, Math.round(score)));
  const color = matchColor(clamped);
  const r = (size - strokeWidth) / 2;
  const c = 2 * Math.PI * r;
  const offset = c * (1 - clamped / 100);
  return (
    <span
      role="img"
      aria-label={ariaLabel ?? `${clamped}%`}
      className="relative inline-flex shrink-0 items-center justify-center"
      style={{ width: size, height: size }}
    >
      <svg width={size} height={size} className="-rotate-90" aria-hidden>
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke="var(--fit-track)"
          strokeWidth={strokeWidth}
        />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke={color}
          strokeWidth={strokeWidth}
          strokeDasharray={c}
          strokeDashoffset={offset}
          strokeLinecap="round"
        />
      </svg>
      <span
        className="absolute font-semibold tabular-nums"
        style={{ color, fontSize: Math.round(size * 0.32) }}
      >
        {clamped}
      </span>
    </span>
  );
}
