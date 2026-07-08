import { WorkspacePlaceholder } from "@/components/layout/workspace-placeholder";

export default async function StudentCatchAll({
  params,
}: {
  params: Promise<{ slug: string[] }>;
}) {
  const { slug } = await params;
  return <WorkspacePlaceholder persona="student" slug={slug} />;
}
