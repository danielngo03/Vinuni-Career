import { PublicJobDetail } from "@/components/jobs/public-job-detail";

export default async function PublicJobDetailPage({
  params,
}: {
  params: Promise<{ jobId: string }>;
}) {
  const { jobId } = await params;
  return <PublicJobDetail jobId={jobId} />;
}
