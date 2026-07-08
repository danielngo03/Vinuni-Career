"use client";

import { useTranslations } from "next-intl";
import { useQuery } from "@tanstack/react-query";
import { Fire, ChartLineUp } from "@phosphor-icons/react";
import { jobsApi, type CompetitionLevel } from "@/lib/api";
import { Skeleton } from "@/components/ui";

/* ── Level config ─────────────────────────────────────────────────────────── */

interface LevelConfig {
  badgeClass: string;
  iconColorClass: string;
  useFlame: boolean;
}

/* Level scale reuses the v9 meaning-only palette: teal = favorable odds, amber
   = caution, VinUni red = high/very-high competition — intensity (not hue)
   separates high from very_high so the scale stays inside the three semantic
   colors defined in globals.css. */
const LEVEL_CONFIG: Record<CompetitionLevel, LevelConfig> = {
  low: {
    badgeClass: "bg-[var(--teal-50)] text-[var(--teal-700)] border border-[var(--teal-100)]",
    iconColorClass: "text-[var(--teal-600)]",
    useFlame: false,
  },
  medium: {
    badgeClass: "bg-[var(--amber-50)] text-[var(--amber-700)] border border-[var(--amber-100)]",
    iconColorClass: "text-[var(--amber-600)]",
    useFlame: false,
  },
  high: {
    badgeClass: "bg-[var(--red-50)] text-[var(--red-600)] border border-[var(--red-100)]",
    iconColorClass: "text-[var(--red-600)]",
    useFlame: true,
  },
  very_high: {
    badgeClass: "bg-[var(--red-100)] text-[var(--red-700)] border border-[var(--red-400)]",
    iconColorClass: "text-[var(--red-700)]",
    useFlame: true,
  },
};

/* ── Skeleton ─────────────────────────────────────────────────────────────── */

function CompetitionBadgeSkeleton() {
  return (
    <div
      className="rounded-2xl border border-[var(--border-default)] bg-[var(--surface-card)] p-4 shadow-[0_2px_16px_rgba(11,34,57,0.07)] "
      aria-hidden="true"
    >
      <div className="flex items-center justify-between gap-3">
        <Skeleton className="h-4 w-36" />
        <Skeleton className="h-5 w-16 rounded-full" />
      </div>
      <Skeleton className="mt-2.5 h-3 w-full" />
      <Skeleton className="mt-1 h-3 w-4/5" />
    </div>
  );
}

/* ── Main component ───────────────────────────────────────────────────────── */

export function CompetitionBadge({ jobId }: { jobId: string }) {
  const t = useTranslations("jobs");
  const { data, isLoading, isError } = useQuery({
    queryKey: ["jobs", "competition-signal", jobId],
    queryFn: () => jobsApi.competitionSignal(jobId),
    // Signal is public — no retry on 404/5xx; hide silently on failure.
    retry: false,
    // Treat as fresh for 5 minutes; competition data changes slowly.
    staleTime: 5 * 60 * 1000,
  });

  if (isLoading) {
    return <CompetitionBadgeSkeleton />;
  }

  // Hide entirely on error or missing data — this is an enhancement, not
  // critical UI. Students should never see a broken competition signal card.
  if (isError || !data) return null;

  const config = LEVEL_CONFIG[data.level] ?? LEVEL_CONFIG.medium;
  const Icon = config.useFlame ? Fire : ChartLineUp;

  return (
    <div
      className="rounded-2xl border border-[var(--border-default)] bg-[var(--surface-card)] p-4 shadow-[0_2px_16px_rgba(11,34,57,0.07)] "
      role="region"
      aria-label={t("competitionRegionLabel")}
    >
      {/* Header row: title + level badge */}
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Icon
            aria-hidden
            weight="duotone"
            className={`size-4 shrink-0 ${config.iconColorClass}`}
          />
          <span className="text-sm font-semibold text-[var(--text-primary)]">
            {t("competitionTitle")}
          </span>
        </div>
        <span
          className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ${config.badgeClass}`}
        >
          {data.label}
        </span>
      </div>

      {/* AI explanation (only when backend confirms it is available and non-null) */}
      {data.ai_explanation_available && data.explanation ? (
        <p className="mt-2 text-xs leading-relaxed text-[var(--text-secondary)]">
          {data.explanation}
        </p>
      ) : null}

      {/* Disclaimer — always shown */}
      <p className="mt-2 text-[10px] leading-relaxed text-[var(--text-muted)]">
        {t("competitionDisclaimer")}
      </p>
    </div>
  );
}
