import { PartnerJobDetailScreen } from "@/components/jobs/partner-job-detail-screen";

export default async function PartnerJobDetailPage({
  params,
}: {
  params: Promise<{ jobId: string }>;
}) {
  const { jobId } = await params;
  return <PartnerJobDetailScreen jobId={jobId} />;
}
