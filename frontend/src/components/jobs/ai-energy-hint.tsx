"use client";

import { useTranslations } from "next-intl";
import { useQuery } from "@tanstack/react-query";
import { Lightning, ArrowUpRight } from "@phosphor-icons/react";
import { Link } from "@/i18n/navigation";
import { aiAssistantApi } from "@/lib/api";
import { energyGate } from "@/lib/jobs/job-intelligence";
import { cn } from "@/lib/utils";

const BILLING_HREF = "/student/billing";

/**
 * Point-of-action AI energy cost hint, shown at the top of a metered drawer
 * before/while the analysis runs. Reuses the exact masked usage source as the
 * header/sidebar meter (shared `["ai","usage","me"]` query key — one fetch, one
 * cache) so nothing drifts, and surfaces ONLY the remaining energy percentage +
 * a coarse "uses AI energy" note. Never a token, USD, provider, or model value.
 *
 * When the weekly energy is exhausted it becomes a block state that links to
 * top-up/upgrade; the drawer's deterministic content still renders below.
 */
export function AiEnergyHint({
  className,
  variant = "card",
}: {
  className?: string;
  /** `card` = full point-of-action block; `inline` = compact one-line caption. */
  variant?: "card" | "inline";
}) {
  const t = useTranslations("jobs.studentIntel.energy");
  const usage = useQuery({
    queryKey: ["ai", "usage", "me"],
    queryFn: () => aiAssistantApi.myUsage(),
    staleTime: 60_000,
    retry: false,
  });

  const gate = energyGate(usage.data);
  if (!gate) return null;

  if (variant === "inline") {
    return (
      <p
        className={cn(
          "flex items-center gap-1.5 text-[11px] font-medium",
          gate.blocked
            ? "text-[var(--red-600)]"
            : gate.tone === "warn"
              ? "text-[var(--amber-700)]"
              : "text-[var(--text-muted)]",
          className,
        )}
      >
        <Lightning
          aria-hidden
          weight="fill"
          className={cn(
            "size-3.5 shrink-0",
            gate.blocked
              ? "text-[var(--red-600)]"
              : gate.tone === "warn"
                ? "text-[var(--amber-600)]"
                : "text-[var(--teal-600)]",
          )}
        />
        {gate.blocked
          ? t("blockedTitle")
          : `${t("costNote")} · ${t("remaining", { pct: gate.pct })}`}
      </p>
    );
  }

  if (gate.blocked) {
    return (
      <div
        className={cn(
          "rounded-xl border border-[var(--red-600)]/30 bg-[var(--red-50)] px-3.5 py-3",
          className,
        )}
      >
        <p className="flex items-center gap-2 text-xs font-semibold text-[var(--red-600)]">
          <Lightning aria-hidden weight="fill" className="size-4 shrink-0" />
          {t("blockedTitle")}
        </p>
        <p className="mt-1 text-[11px] leading-relaxed text-[var(--text-secondary)]">
          {t("blockedBody")}
        </p>
        <Link
          href={BILLING_HREF}
          className="mt-2 inline-flex items-center gap-1 text-[11px] font-bold text-[var(--brand-primary)] outline-none hover:underline focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/30"
        >
          {t("manage")}
          <ArrowUpRight aria-hidden weight="bold" className="size-3" />
        </Link>
      </div>
    );
  }

  const isWarn = gate.tone === "warn";
  return (
    <div
      className={cn(
        "flex items-center justify-between gap-3 rounded-xl border px-3.5 py-2.5",
        isWarn
          ? "border-[var(--amber-500)]/40 bg-[var(--amber-50)]"
          : "border-[var(--border-default)] bg-[var(--surface-secondary)]",
        className,
      )}
    >
      <span className="flex items-center gap-1.5 text-[11px] font-medium text-[var(--text-secondary)]">
        <Lightning
          aria-hidden
          weight="fill"
          className={cn(
            "size-3.5 shrink-0",
            isWarn ? "text-[var(--amber-600)]" : "text-[var(--teal-600)]",
          )}
        />
        {t("costNote")}
      </span>
      <span
        className={cn(
          "text-[11px] font-semibold tabular-nums",
          isWarn ? "text-[var(--amber-700)]" : "text-[var(--text-secondary)]",
        )}
      >
        {t("remaining", { pct: gate.pct })}
      </span>
    </div>
  );
}
