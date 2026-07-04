import { CvBuilderScreen } from "@/components/cv/cv-builder-screen";

export default async function StudentCvBuilderPage({
  params,
  searchParams,
}: {
  params: Promise<{ cvId: string }>;
  searchParams: Promise<{ suggest?: string; job?: string }>;
}) {
  const { cvId } = await params;
  const { suggest, job } = await searchParams;
  return <CvBuilderScreen cvId={cvId} initialSuggestionId={suggest} jobId={job} />;
}
