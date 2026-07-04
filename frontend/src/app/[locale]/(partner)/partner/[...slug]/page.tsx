import { WorkspacePlaceholder } from "@/components/layout/workspace-placeholder";

export default async function PartnerCatchAll({
  params,
}: {
  params: Promise<{ slug: string[] }>;
}) {
  const { slug } = await params;
  return <WorkspacePlaceholder persona="partner" slug={slug} />;
}
