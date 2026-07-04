import { PartnerPipelineBoard } from "@/components/applications/partner-pipeline-board";

export default async function PartnerJobPipelinePage({
  params,
}: {
  params: Promise<{ jobId: string }>;
}) {
  const { jobId } = await params;
  return <PartnerPipelineBoard jobId={jobId} />;
}
