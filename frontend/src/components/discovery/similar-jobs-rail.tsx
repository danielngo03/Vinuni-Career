"use client";

import { useId } from "react";
import { useTranslations } from "next-intl";
import { useQuery } from "@tanstack/react-query";
import { Stack } from "@phosphor-icons/react";
import { Skeleton } from "@/components/ui";
import { RecommendedJobCard } from "./recommended-job-card";
import { discoveryApi } from "@/lib/api";

/**
 * "Similar jobs" rail on the public job detail (spec §6). Deterministic
 * skill/role-family overlap from the backend. Hidden entirely when there are no
 * genuinely similar jobs (never padded with unrelated roles). A transient error
 * also hides the rail — it is a secondary surface and must not break the page.
 */
export function SimilarJobsRail({ jobId }: { jobId: string }) {
  const t = useTranslations("discovery");
  const renderId = useId();

  const query = useQuery({
    queryKey: ["jobs", "similar", jobId],
    queryFn: () => discoveryApi.similar(jobId, 6),
    retry: false,
  });

  if (query.isError) return null;

  if (query.isPending) {
    return (
      <section className="mt-12">
        <Skeleton className="mb-4 h-6 w-48" />
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} className="h-[200px] rounded-xl" />
          ))}
        </div>
      </section>
    );
  }

  const items = query.data?.items ?? [];
  if (items.length === 0) return null;

  return (
    <section className="mt-12" aria-labelledby={`${renderId}-similar`}>
      <h2
        id={`${renderId}-similar`}
        className="mb-4 flex items-center gap-2 text-xl font-bold tracking-tight text-[var(--text-primary)]"
      >
        <span className="flex size-7 shrink-0 items-center justify-center rounded-lg icon-chip-primary shadow-sm">
          <Stack aria-hidden weight="duotone" className="size-4 text-white" />
        </span>
        {t("similarTitle")}
      </h2>
      <ul className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {items.map((item) => (
          <RecommendedJobCard
            key={item.id}
            item={item}
            surface="job_detail_similar"
            renderId={renderId}
            showScore={false}
          />
        ))}
      </ul>
    </section>
  );
}
