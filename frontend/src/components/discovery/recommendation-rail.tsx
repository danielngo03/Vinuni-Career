"use client";

import { useId } from "react";
import { useTranslations } from "next-intl";
import { Sparkle, Clock, TrendUp, ArrowRight } from "@phosphor-icons/react";
import { Link } from "@/i18n/navigation";
import { JobRow } from "@/components/jobs/job-row";
import { RecommendedJobCard } from "./recommended-job-card";
import { railSurface } from "@/lib/discovery/analytics";
import { cn } from "@/lib/utils";
import type { CoarseSignalTags, JobRecommendations, RecoSource } from "@/lib/api";

/**
 * Recommendation rail (homepage / search). The heading is labelled HONESTLY by
 * `data.source`: "Đề xuất cho bạn" only when the ranking was personalized,
 * otherwise "Mới tuần này" (recent) / "Phổ biến với sinh viên VinUni" (popular).
 * Hidden entirely when there are no items. Each card resolves its own
 * inventory-classed analytics surface (sponsored items override + carry the
 * placement id).
 */
export function RecommendationRail({
  data,
  base,
  signalTags,
  viewAllHref,
  className,
  layout = "cards",
  showSubtitle = true,
  maxItems,
}: {
  data: JobRecommendations;
  base: "homepage" | "search";
  signalTags?: CoarseSignalTags;
  viewAllHref?: string;
  className?: string;
  layout?: "cards" | "dense";
  showSubtitle?: boolean;
  maxItems?: number;
}) {
  const t = useTranslations("discovery");
  const renderId = useId();

  if (!data || data.items.length === 0) return null;

  const meta = railMeta(data.source);
  const items = maxItems ? data.items.slice(0, maxItems) : data.items;

  return (
    <section className={className} aria-labelledby={`${renderId}-heading`}>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2
            id={`${renderId}-heading`}
            className="flex items-center gap-2.5 text-xl font-bold tracking-tight text-[var(--text-primary)]"
          >
            <span className={cn("flex size-7 shrink-0 items-center justify-center rounded-lg shadow-sm", meta.iconGradient)}>
              <meta.icon aria-hidden weight="duotone" className="size-4 text-white" />
            </span>
            {t(meta.titleKey)}
          </h2>
          {showSubtitle && (
            <p className="mt-0.5 text-sm text-[var(--text-secondary)]">
              {t(meta.subtitleKey)}
            </p>
          )}
        </div>
        {viewAllHref && (
          <Link
            href={viewAllHref}
            className="inline-flex items-center gap-1 text-sm font-semibold text-[var(--brand-primary)] outline-none hover:underline focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/30"
          >
            {t("viewAll")}
            <ArrowRight aria-hidden weight="bold" className="size-4" />
          </Link>
        )}
      </div>

      <ul className={cn(layout === "dense" ? "marketplace-card overflow-hidden rounded-[16px]" : "grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3")}>
        {items.map((item) =>
          layout === "dense" ? (
            <li key={item.id} className="border-b border-[var(--border-default)] last:border-b-0">
              <JobRow job={item} density="compact" />
            </li>
          ) : (
            <RecommendedJobCard
              key={item.id}
              item={item}
              surface={railSurface(base, item.source)}
              renderId={renderId}
              signalTags={signalTags}
            />
          ),
        )}
      </ul>
    </section>
  );
}

function railMeta(source: RecoSource): {
  titleKey: string;
  subtitleKey: string;
  icon: React.ElementType;
  iconGradient: string;
} {
  switch (source) {
    case "recommended":
      return {
        titleKey: "rail.recommendedTitle",
        subtitleKey: "rail.recommendedSubtitle",
        icon: Sparkle,
        iconGradient: "icon-chip-info",
      };
    case "popular":
      return {
        titleKey: "rail.popularTitle",
        subtitleKey: "rail.popularSubtitle",
        icon: TrendUp,
        iconGradient: "icon-chip-primary",
      };
    default:
      return {
        titleKey: "rail.recentTitle",
        subtitleKey: "rail.recentSubtitle",
        icon: Clock,
        iconGradient: "icon-chip-success",
      };
  }
}
