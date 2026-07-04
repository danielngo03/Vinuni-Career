import { WorkspacePlaceholder } from "@/components/layout/workspace-placeholder";

export default async function UniversityCatchAll({
  params,
}: {
  params: Promise<{ slug: string[] }>;
}) {
  const { slug } = await params;
  return <WorkspacePlaceholder persona="university" slug={slug} />;
}
