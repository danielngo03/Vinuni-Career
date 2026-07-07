"use client";

import { useTranslations } from "next-intl";
import { cn } from "@/lib/utils";
import type { ApplicantFitBand } from "@/lib/api";

/**
 * Fit-band styling on the v9 Monochrome ramp. Green is reserved for the STRONG
 * (verified-strength) signal; every other band uses the ink/gray hierarchy so
 * the chip never competes with real semantic color and never uses blue/navy.
 */
const BAND_STYLE: Record<ApplicantFitBand, string> = {
  strong: "border-emerald-300 bg-emerald-50 text-emerald-700",
  good: "border-[var(--border-strong)] bg-[var(--bg-subtle)] text-[var(--text-primary)]",
  fair: "border-[var(--border-default)] bg-[var(--bg-subtle)] text-[var(--text-secondary)]",
  weak: "border-[var(--border-subtle)] bg-transparent text-[var(--text-muted)]",
};

/**
 * Compact, assistive CV↔JD fit chip: the 0-100 PRODUCT score + band label.
 * Advisory only — it never drives an automated decision. When the candidate is
 * unscored (`score`/`band` null) it renders a neutral "—" state, never a
 * fabricated `0`. The score is announced to assistive tech as
 * "CV–JD fit N out of 100, <band>".
 */
export function FitChip({
  score,
  band,
  size = "sm",
  className,
}: {
  score: number | null;
  band: ApplicantFitBand | null;
  size?: "sm" | "md";
  className?: string;
}) {
  const t = useTranslations("candidates");
  const pad = size === "sm" ? "px-2 py-0.5 text-[11px]" : "px-2.5 py-1 text-xs";

  if (score === null || band === null) {
    return (
      <span
        aria-label={t("fitUnscoredAria")}
        className={cn(
          "inline-flex items-center gap-1 rounded-full border border-dashed border-[var(--border-default)] bg-transparent font-semibold text-[var(--text-muted)]",
          pad,
          className,
        )}
      >
        <span aria-hidden>—</span>
        <span aria-hidden className="font-normal">
          {t("fitUnscored")}
        </span>
      </span>
    );
  }

  const bandLabel = t(`fitBand.${band}`);
  return (
    <span
      aria-label={t("fitScoreAria", { score, band: bandLabel })}
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border font-semibold tabular-nums",
        BAND_STYLE[band],
        pad,
        className,
      )}
    >
      <span aria-hidden>{score}</span>
      <span aria-hidden className="opacity-50">
        ·
      </span>
      <span aria-hidden className="font-medium">
        {bandLabel}
      </span>
    </span>
  );
}
