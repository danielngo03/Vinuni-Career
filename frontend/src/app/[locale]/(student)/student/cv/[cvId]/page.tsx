import { CvDetailScreen } from "@/components/cv/cv-detail-screen";

export default async function StudentCvDetailPage({
  params,
  searchParams,
}: {
  params: Promise<{ cvId: string }>;
  searchParams: Promise<{ suggest?: string; job?: string }>;
}) {
  const { cvId } = await params;
  const { suggest, job } = await searchParams;
  return <CvDetailScreen cvId={cvId} initialSuggestionId={suggest} jobId={job} />;
}
