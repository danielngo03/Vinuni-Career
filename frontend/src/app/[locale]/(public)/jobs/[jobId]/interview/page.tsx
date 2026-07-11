"use client";

import { use } from "react";
import { useQuery } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { jobsApi } from "@/lib/api";
import { MockInterviewScreen } from "@/components/jobs/mock-interview/mock-interview-screen";
import { EmptyState, Skeleton } from "@/components/ui";
import { WarningCircle } from "@phosphor-icons/react";

export default function InterviewPage({
  params,
}: {
  params: Promise<{ jobId: string }>;
}) {
  const { jobId } = use(params);
  const t = useTranslations("jobs.mockInterview");

  // Confirm the job is visible before entering the room; the screen itself
  // fetches prep + drives the session. Real skeleton/error states, no fakes.
  const jobQuery = useQuery({
    queryKey: ["jobs", "public", jobId],
    queryFn: () => jobsApi.getPublic(jobId),
    retry: false,
    staleTime: 5 * 60 * 1000,
  });

  if (jobQuery.isPending) {
    return (
      <div className="mx-auto max-w-2xl space-y-4 px-4 py-12">
        <Skeleton className="h-5 w-24" />
        <Skeleton className="h-8 w-2/3" />
        <Skeleton className="h-4 w-1/2" />
        <Skeleton className="mt-8 h-40 rounded-2xl" />
      </div>
    );
  }

  if (jobQuery.isError) {
    return (
      <div className="mx-auto max-w-2xl px-4 py-12">
        <EmptyState
          kind="error"
          icon={WarningCircle}
          title={t("screenErrorTitle")}
          description={t("screenErrorBody")}
        />
      </div>
    );
  }

  return <MockInterviewScreen jobId={jobId} />;
}
