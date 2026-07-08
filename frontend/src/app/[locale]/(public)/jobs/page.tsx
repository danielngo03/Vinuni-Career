import { Suspense } from "react";
import { PublicJobBoard } from "@/components/jobs/public-job-board";

export default function PublicJobsPage() {
  // PublicJobBoard reads the `?q=` query via useSearchParams, which requires a
  // Suspense boundary for static rendering in the App Router.
  return (
    <Suspense>
      <PublicJobBoard />
    </Suspense>
  );
}
