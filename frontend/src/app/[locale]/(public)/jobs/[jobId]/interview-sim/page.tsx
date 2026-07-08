"use client";

import { use } from "react";
import { useQuery } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { jobsApi } from "@/lib/api";
import { InterviewSimulatorScreen } from "@/components/jobs/interview-simulator-screen";
import { Skeleton } from "@/components/ui";

export default function InterviewSimPage({
  params,
}: {
  params: Promise<{ jobId: string }>;
}) {
  const { jobId } = use(params);
  const t = useTranslations("jobs.interviewSim");

  const jobQuery = useQuery({
    queryKey: ["jobs", "public", jobId],
    queryFn: () => jobsApi.getPublic(jobId),
    retry: false,
    staleTime: 5 * 60 * 1000,
  });

  if (jobQuery.isPending) {
    return (
      <div className="mx-auto max-w-2xl space-y-4 px-4 py-12">
        <Skeleton className="h-6 w-48" />
        <Skeleton className="h-5 w-32" />
        <Skeleton className="mt-8 h-64 rounded-2xl" />
      </div>
    );
  }

  if (jobQuery.isError) {
    return (
      <div className="flex min-h-[60vh] flex-col items-center justify-center">
        <p className="text-sm text-[var(--text-muted)]">{t("loadError")}</p>
      </div>
    );
  }

  const job = jobQuery.data;

  return (
    <InterviewSimulatorScreen
      jobId={jobId}
      jobTitle={job?.title ?? ""}
      companyName={job?.company?.display_name}
    />
  );
}
