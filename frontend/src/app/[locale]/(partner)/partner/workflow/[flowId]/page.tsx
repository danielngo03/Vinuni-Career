import { WorkflowBuilderScreen } from "@/components/workflow/workflow-builder-screen";

export default async function PartnerWorkflowEditPage({
  params,
}: {
  params: Promise<{ flowId: string }>;
}) {
  const { flowId } = await params;
  return <WorkflowBuilderScreen flowId={flowId} ownerType="partner" />;
}
