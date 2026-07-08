"use client";

import { useTranslations } from "next-intl";
import { Microphone } from "@phosphor-icons/react";
import { useRouter } from "@/i18n/navigation";
import { Button } from "@/components/ui";

/**
 * Student-gated entry point for the AI mock interview, shown in the job-detail
 * sidebar next to interview prep. Navigates to the dedicated interview room.
 */
export function MockInterviewEntryCard({ jobId }: { jobId: string }) {
  const t = useTranslations("jobs.mockInterview");
  const router = useRouter();

  return (
    <div className="marketplace-card mt-4 rounded-[16px] p-4">
      <div className="flex items-start gap-3">
        <span className="flex size-9 shrink-0 items-center justify-center rounded-xl icon-chip-primary shadow-sm">
          <Microphone aria-hidden weight="duotone" className="size-5" />
        </span>
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <h2 className="text-sm font-bold tracking-tight text-[var(--text-primary)]">
              {t("entryTitle")}
            </h2>
            <span className="rounded-full bg-[var(--bg-muted)] px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-[var(--text-secondary)]">
              {t("voiceBadge")}
            </span>
          </div>
          <p className="mt-1 text-xs leading-relaxed text-[var(--text-muted)]">
            {t("entrySubtitle")}
          </p>
        </div>
      </div>
      <Button
        variant="primary"
        size="sm"
        fullWidth
        className="mt-3.5"
        onClick={() => router.push(`/jobs/${jobId}/interview`)}
      >
        <Microphone aria-hidden weight="bold" className="size-4" />
        {t("entryCta")}
      </Button>
    </div>
  );
}
