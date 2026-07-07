"use client";

import { useQuery } from "@tanstack/react-query";
import { cvApi } from "@/lib/api";
import { CvBuilderScreen } from "./cv-builder-screen";
import { UploadedCvView } from "./uploaded-cv-view";

/**
 * Routes a CV detail URL to the right surface: uploaded CVs get the read-only
 * original-document view; template-created CVs get the editable builder. Uses the
 * same query key as the builder so the fetch is de-duped (no double request).
 */
export function CvDetailScreen({
  cvId,
  initialSuggestionId,
  jobId,
}: {
  cvId: string;
  initialSuggestionId?: string;
  jobId?: string;
}) {
  const query = useQuery({
    queryKey: ["cv", "detail", cvId],
    queryFn: () => cvApi.get(cvId),
  });

  // While the type is unknown, show a light skeleton rather than briefly flashing
  // the builder for what may be an uploaded CV.
  if (query.isPending) {
    return (
      <div className="h-[60vh] animate-pulse rounded-xl border border-[var(--glass-border-strong)] bg-[var(--glass-surface)]" />
    );
  }

  if (query.data?.is_uploaded) {
    return <UploadedCvView detail={query.data} />;
  }

  return (
    <CvBuilderScreen cvId={cvId} initialSuggestionId={initialSuggestionId} jobId={jobId} />
  );
}
