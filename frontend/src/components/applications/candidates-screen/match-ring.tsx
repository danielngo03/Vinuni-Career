"use client";

import type { ChipTone } from "@/components/kit";
import { fitColor, fitTier, type FitTier } from "@/lib/cv/fit";

/**
 * MatchRing — compact CV↔JD fit gauge. A colorblind-safe ring (emerald/amber/
 * rose bands, driven purely by the numeric PRODUCT score — never an AI
 * confidence rating) with the score in the center. Used both as a list column
 * and, larger, in the candidate detail drawer header. Renders a neutral
 * placeholder when no score is available so the column never fabricates a value.
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
  const color = fitColor(clamped);
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
          stroke="var(--bg-muted)"
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

/** i18n key for the tier label of a score, for a small chip next to the ring. */
export function fitTierKey(score: number): `matchTier${Capitalize<FitTier>}` {
  const tier = fitTier(score);
  return (
    tier === "strong" ? "matchTierStrong" : tier === "mid" ? "matchTierMid" : "matchTierWeak"
  );
}

/** Semantic StatusChip tone for a fit score (emerald / amber / red bands). */
export function fitChipTone(score: number): ChipTone {
  const tier = fitTier(score);
  return tier === "strong" ? "success" : tier === "mid" ? "warning" : "danger";
}
