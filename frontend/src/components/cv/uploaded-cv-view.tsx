"use client";

import { useTranslations } from "next-intl";
import { ArrowLeft, ArrowSquareOut, FileArrowDown, Sparkle } from "@phosphor-icons/react";
import { useRouter } from "@/i18n/navigation";
import { Button } from "@/components/ui";
import type { CvDetail } from "@/lib/api";

/**
 * Read-only view of an UPLOADED CV (the student's own PDF/image). Uploaded CVs are
 * never edited in the builder — the student already has the document; the system
 * just extracted + stored it for CV–JD matching. This surface shows the original
 * file and library actions only. The editable builder is reserved for
 * template-created CVs (owner decision 2026-07-05).
 */
export function UploadedCvView({ detail }: { detail: CvDetail }) {
  const t = useTranslations("cv.uploaded");
  const router = useRouter();
  const url = detail.original_preview_url ?? null;

  const sectionCount = detail.sections.filter((s) => {
    const c = s.content as { items?: unknown[]; entries?: unknown[] } | undefined;
    return (c?.items?.length ?? 0) > 0 || (c?.entries?.length ?? 0) > 0;
  }).length;

  return (
    <div>
      <div className="mb-4">
        <button
          type="button"
          onClick={() => router.push("/student/cv")}
          className="inline-flex items-center gap-1.5 rounded-lg px-2 py-1 text-sm font-medium text-[var(--text-secondary)] outline-none hover:text-[var(--brand-primary)] focus-visible:underline"
        >
          <ArrowLeft aria-hidden weight="bold" className="size-4" />
          {t("backToLibrary")}
        </button>
      </div>

      <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <h1 className="truncate text-xl font-bold text-[var(--text-primary)]">
              {detail.title}
            </h1>
            <span className="shrink-0 rounded-full bg-[var(--glass-surface-heavy)] px-2.5 py-0.5 text-xs font-semibold text-[var(--text-secondary)]">
              {t("badge")}
            </span>
          </div>
          <p className="mt-1 flex items-center gap-1.5 text-xs text-[var(--text-secondary)]">
            <Sparkle aria-hidden weight="duotone" className="size-3.5 text-[var(--brand-primary)]" />
            {t("note", { count: sectionCount })}
          </p>
        </div>
        {url ? (
          <div className="flex shrink-0 gap-2">
            <a href={url} target="_blank" rel="noopener noreferrer">
              <Button variant="secondary" size="sm">
                <ArrowSquareOut aria-hidden weight="bold" className="size-4" />
                {t("openOriginal")}
              </Button>
            </a>
            <a href={url} download>
              <Button variant="ghost" size="sm">
                <FileArrowDown aria-hidden weight="bold" className="size-4" />
                {t("download")}
              </Button>
            </a>
          </div>
        ) : null}
      </div>

      <div className="mt-4 overflow-hidden rounded-xl border border-[var(--glass-border-strong)] bg-[var(--glass-surface)] shadow-[var(--shadow-sm)]">
        {url ? (
          <iframe
            title={detail.title}
            src={url}
            className="h-[78vh] w-full bg-white"
          />
        ) : (
          <div className="flex h-[40vh] items-center justify-center p-6 text-center text-sm text-[var(--text-secondary)]">
            {t("unavailable")}
          </div>
        )}
      </div>
    </div>
  );
}
