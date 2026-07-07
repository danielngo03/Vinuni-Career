"use client";

import { useRouter } from "@/i18n/navigation";
import { JobForm } from "./job-form";

export function PartnerNewJobScreen() {
  const router = useRouter();

  return (
    <>
      <JobForm
        mode="create"
        onSuccess={(job) => router.push(`/partner/jobs/${job.id}`)}
        onCancel={() => router.push("/partner/jobs")}
      />
    </>
  );
}
