"use client";

import { useTranslations } from "next-intl";
import { useQuery } from "@tanstack/react-query";
import {
  ArrowSquareOut,
  FilePdf,
  ShieldWarning,
  WarningCircle,
} from "@phosphor-icons/react";
import { Button, Skeleton } from "@/components/ui";
import { applicationsApi, resolveDownloadUrl } from "@/lib/api";

/**
 * Embedded, watermarked CV preview pinned inside the candidate review drawer.
 * Uses the same signed snapshot URL as the Download action
 * (`applicationsApi.getCvDownload`) rendered in an <iframe> so the recruiter can
 * read the CV without leaving the drawer. Honors `cv_download_available`: when
 * the CV is blocked (anonymous + unrevealed) it shows the reveal-required state
 * and does NOT fetch a URL. Always offers an "open in new tab" fallback.
 */
export function CvPreviewPane({
  applicationId,
  available,
  displayName,
}: {
  applicationId: string;
  available: boolean;
  displayName: string;
}) {
  const t = useTranslations("candidates");
  const tc = useTranslations("common");

  const query = useQuery({
    queryKey: ["applications", "cvDownload", applicationId],
    queryFn: () => applicationsApi.getCvDownload(applicationId),
    enabled: available,
    staleTime: 4 * 60 * 1000,
    retry: false,
  });

  if (!available) {
    return (
      <div className="flex h-full min-h-[220px] flex-col items-center justify-center gap-2 rounded-xl border border-dashed border-[var(--border-default)] bg-[var(--bg-subtle)]/40 p-6 text-center">
        <ShieldWarning
          aria-hidden
          weight="duotone"
          className="size-6 text-[var(--text-muted)]"
        />
        <p className="text-sm font-semibold text-[var(--text-primary)]">
          {t("cvUnavailableTitle")}
        </p>
        <p className="text-xs text-[var(--text-muted)]">{t("downloadBlocked")}</p>
      </div>
    );
  }

  const url = query.data ? resolveDownloadUrl(query.data.download_url) : null;

  return (
    <div className="flex h-full min-h-[50vh] flex-col gap-2 lg:min-h-0">
      <div className="flex items-center justify-between gap-2">
        <p className="flex items-center gap-1.5 text-xs font-semibold text-[var(--text-secondary)]">
          <FilePdf aria-hidden weight="duotone" className="size-4" />
          {t("cvPreviewLabel")}
        </p>
        {url && (
          <a
            href={url}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1 rounded-lg text-xs font-medium text-[var(--text-secondary)] outline-none hover:text-[var(--text-primary)] focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/30"
          >
            <ArrowSquareOut aria-hidden weight="bold" className="size-3.5" />
            {t("cvOpenNewTab")}
          </a>
        )}
      </div>

      <div className="relative min-h-[50vh] flex-1 overflow-hidden rounded-xl border border-[var(--border-default)] bg-[var(--bg-subtle)]/30 lg:min-h-0">
        {query.isPending ? (
          <div className="flex h-full min-h-[50vh] flex-col gap-3 p-4">
            <Skeleton className="h-4 w-1/2" />
            <Skeleton className="h-4 w-3/4" />
            <Skeleton className="h-40 w-full" />
            <Skeleton className="h-4 w-2/3" />
            <Skeleton className="h-4 w-1/2" />
          </div>
        ) : query.isError || !url ? (
          <div className="flex h-full min-h-[50vh] flex-col items-center justify-center gap-2 p-6 text-center">
            <WarningCircle
              aria-hidden
              weight="duotone"
              className="size-6 text-[var(--brand-red)]"
            />
            <p className="text-sm text-[var(--text-secondary)]">
              {t("cvPreviewError")}
            </p>
            <Button
              variant="secondary"
              size="sm"
              onClick={() => query.refetch()}
            >
              {tc("retry")}
            </Button>
          </div>
        ) : (
          <iframe
            title={t("cvPreviewIframeTitle", { name: displayName })}
            src={url}
            className="h-full min-h-[50vh] w-full border-0 bg-white"
          />
        )}
      </div>

      {query.data?.has_watermark && (
        <p className="flex items-start gap-1.5 text-[11px] text-[var(--text-muted)]">
          <ShieldWarning
            aria-hidden
            weight="duotone"
            className="mt-px size-3.5 shrink-0"
          />
          {t("watermarkNote")}
        </p>
      )}
    </div>
  );
}
