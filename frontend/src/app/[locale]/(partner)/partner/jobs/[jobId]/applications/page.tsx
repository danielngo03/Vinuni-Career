import { PartnerCandidatesScreen } from "@/components/applications/partner-candidates-screen";

export default async function PartnerJobApplicationsPage({
  params,
}: {
  params: Promise<{ jobId: string }>;
}) {
  const { jobId } = await params;
  return <PartnerCandidatesScreen jobId={jobId} />;
}
