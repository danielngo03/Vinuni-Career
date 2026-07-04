"use client";

import { useTranslations } from "next-intl";
import { ArrowRight, Info, UploadSimple } from "@phosphor-icons/react";
import { Button } from "@/components/ui";
import { CvOriginalPreview, formatBytes } from "../cv-original-preview";
import type { UploadPreview } from "@/lib/api";

/** Step: preview (before ingestion). */
export function PreviewStep({
  preview,
  onUse,
  onAnother,
}: {
  preview: UploadPreview;
  onUse: () => void;
  onAnother: () => void;
}) {
  const t = useTranslations("cv.import");
  return (
    <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_300px]">
      <div className="min-h-[460px] overflow-hidden rounded-xl border border-[var(--glass-border-strong)] bg-[var(--glass-surface)] backdrop-blur-md shadow-[var(--shadow-sm)]">
        <CvOriginalPreview preview={preview} className="h-full" />
      </div>
      <aside className="lg:sticky lg:top-4">
        <div className="rounded-xl border border-[var(--glass-border-strong)] bg-[var(--glass-surface)] backdrop-blur-md p-4 shadow-[var(--shadow-sm)]">
          <h2 className="text-sm font-bold text-[var(--text-primary)]">
            {t("previewDecisionTitle")}
          </h2>
          <p className="mt-1 text-xs text-[var(--text-secondary)]">
            {t("previewDecisionBody")}
          </p>
          <dl className="mt-3 space-y-1.5 text-xs">
            <div className="flex justify-between gap-2">
              <dt className="text-[var(--text-muted)]">{t("fileLabel")}</dt>
              <dd className="min-w-0 truncate font-medium text-[var(--text-primary)]" title={preview.filename}>
                {preview.filename}
              </dd>
            </div>
            <div className="flex justify-between gap-2">
              <dt className="text-[var(--text-muted)]">{t("sizeLabel")}</dt>
              <dd className="font-medium text-[var(--text-primary)]">
                {formatBytes(preview.size)}
              </dd>
            </div>
            {preview.page_count ? (
              <div className="flex justify-between gap-2">
                <dt className="text-[var(--text-muted)]">{t("pagesLabel")}</dt>
                <dd className="font-medium text-[var(--text-primary)]">
                  {preview.page_count}
                </dd>
              </div>
            ) : null}
          </dl>
          <div className="mt-4 flex flex-col gap-2">
            <Button variant="primary" fullWidth onClick={onUse}>
              <ArrowRight aria-hidden weight="bold" className="size-4" />
              {t("useThisCv")}
            </Button>
            <Button variant="secondary" fullWidth onClick={onAnother}>
              <UploadSimple aria-hidden weight="bold" className="size-4" />
              {t("chooseDifferent")}
            </Button>
          </div>
          <p className="mt-3 flex items-start gap-1.5 text-[11px] leading-relaxed text-[var(--text-muted)]">
            <Info aria-hidden weight="duotone" className="mt-px size-3.5 shrink-0" />
            {t("previewPrivacyNote")}
          </p>
        </div>
      </aside>
    </div>
  );
}
