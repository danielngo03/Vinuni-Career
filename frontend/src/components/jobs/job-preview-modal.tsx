"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { useQuery } from "@tanstack/react-query";
import { Eye, EyeSlash, GraduationCap, WarningCircle } from "@phosphor-icons/react";
import { Button, Modal, Skeleton, EmptyState } from "@/components/ui";
import { cn } from "@/lib/utils";
import { jobsApi, type JobPreviewPersona } from "@/lib/api";
import { JobPreviewContent } from "./job-preview-content";

/**
 * "Preview as guest" / "Preview as student" — lets a partner see exactly what
 * `GET /jobs/{job_id}/preview` would render for that persona, pre- or
 * post-publish. Always clearly labeled as a preview, never the live page.
 */
export function JobPreviewButtons({ jobId }: { jobId: string }) {
  const t = useTranslations("jobs");
  const [persona, setPersona] = useState<JobPreviewPersona | null>(null);

  return (
    <>
      <Button variant="ghost" size="sm" onClick={() => setPersona("guest")}>
        <Eye aria-hidden weight="duotone" className="size-4" />
        {t("preview.guestCta")}
      </Button>
      <Button variant="ghost" size="sm" onClick={() => setPersona("student")}>
        <GraduationCap aria-hidden weight="duotone" className="size-4" />
        {t("preview.studentCta")}
      </Button>
      <JobPreviewModal jobId={jobId} persona={persona} onClose={() => setPersona(null)} />
    </>
  );
}

function JobPreviewModal({
  jobId,
  persona,
  onClose,
}: {
  jobId: string;
  persona: JobPreviewPersona | null;
  onClose: () => void;
}) {
  const t = useTranslations("jobs");
  const tc = useTranslations("common");
  const tStates = useTranslations("states");

  const query = useQuery({
    queryKey: ["jobs", "preview", jobId, persona],
    queryFn: () => jobsApi.preview(jobId, persona as JobPreviewPersona),
    enabled: persona !== null,
    retry: false,
  });

  return (
    <Modal
      open={persona !== null}
      onClose={onClose}
      title={persona === "student" ? t("preview.studentTitle") : t("preview.guestTitle")}
      description={t("preview.modalNote")}
      size="lg"
      closeLabel={tc("close")}
    >
      {query.isPending ? (
        <div className="space-y-3">
          <Skeleton className="h-6 w-2/3" />
          <Skeleton className="h-4 w-1/2" />
          <Skeleton className="h-40 w-full" />
        </div>
      ) : query.isError ? (
        <EmptyState
          kind="error"
          icon={WarningCircle}
          title={tStates("errorTitle")}
          description={tStates("errorBody")}
        />
      ) : query.data ? (
        <div className="space-y-4">
          <div
            className={cn(
              "flex items-start gap-2.5 rounded-xl border px-3.5 py-2.5 text-sm",
              query.data.would_be_visible
                ? "border-[var(--teal-500)]/30 bg-[var(--teal-50)] text-[var(--teal-700)]"
                : "border-[var(--amber-600)]/40 bg-[var(--amber-100)] text-[var(--amber-700)]",
            )}
          >
            {query.data.would_be_visible ? (
              <Eye aria-hidden weight="fill" className="mt-0.5 size-4 shrink-0" />
            ) : (
              <EyeSlash aria-hidden weight="fill" className="mt-0.5 size-4 shrink-0" />
            )}
            <span className="font-medium">
              {query.data.would_be_visible
                ? t("preview.visibleNote")
                : query.data.hidden_reason === "invitation_only"
                  ? t("preview.hiddenInvitationOnly")
                  : t("preview.hiddenVisibilityTier")}
            </span>
          </div>
          <JobPreviewContent job={query.data.preview} />
        </div>
      ) : null}
    </Modal>
  );
}
