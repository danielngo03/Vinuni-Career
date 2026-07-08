"use client";

import { useTranslations } from "next-intl";
import { CheckCircle, Copy, Eye, PencilSimple, Trash } from "@phosphor-icons/react";
import { Button, StatusBadge } from "@/components/ui";
import { formatDateTime } from "@/lib/format";
import type { CvSummary } from "@/lib/api";
import { CvLanguageBadge } from "@/components/cv/cv-language-badge";

export function CvLibraryCard({
  cv,
  locale,
  busy,
  onOpen,
  onDuplicate,
  onDelete,
}: {
  cv: CvSummary;
  locale: string;
  busy: boolean;
  onOpen: () => void;
  onDuplicate: () => void;
  onDelete: () => void;
}) {
  const t = useTranslations("cv");
  // Uploaded CVs are read-only (the student's own document) — they are viewed,
  // not edited in the builder (owner decision 2026-07-05).
  const isUploaded = cv.source_type === "uploaded_import";
  // Library (`ready`) CVs are analyzed and usable to apply / job-fit; a green ✓
  // badge signals readiness. Drafts are unlimited scratch (neutral badge).
  const isReady = cv.status === "ready";

  return (
    <li
      className={`marketplace-card marketplace-card-hover relative flex flex-col overflow-hidden rounded-[14px] p-4 pl-5 before:absolute before:inset-y-0 before:left-0 before:w-1 before:content-[''] ${
        isReady ? "before:bg-[var(--brand-primary)]" : "before:bg-[var(--border-strong)]"
      }`}
    >
      <div className="flex items-start justify-between gap-2">
        <button
          type="button"
          onClick={onOpen}
          className="min-w-0 text-left outline-none focus-visible:underline"
        >
          <span className="flex items-center gap-1.5">
            <h3 className="truncate text-base font-bold text-[var(--text-primary)] hover:text-[var(--brand-primary)]">
              {cv.title}
            </h3>
            <CvLanguageBadge language={cv.language} />
          </span>
        </button>
      </div>

      <div className="mt-2 flex flex-wrap items-center gap-2">
        {isReady ? (
          <StatusBadge tone="verified">
            <CheckCircle aria-hidden weight="fill" className="size-3.5" />
            {t("status.ready")}
          </StatusBadge>
        ) : (
          <StatusBadge tone="draft">{t("status.draft")}</StatusBadge>
        )}
        <span className="text-xs text-[var(--text-muted)]">
          {cv.source_label}
        </span>
      </div>

      <p className="mt-3 text-xs text-[var(--text-secondary)]">
        {t("list.lastEdited", {
          date: formatDateTime(cv.last_edited_at, locale),
        })}
      </p>

      <div className="mt-auto flex flex-wrap gap-1.5 pt-4">
        <Button variant="secondary" size="sm" onClick={onOpen}>
          {isUploaded ? (
            <Eye aria-hidden weight="bold" className="size-4" />
          ) : (
            <PencilSimple aria-hidden weight="bold" className="size-4" />
          )}
          {isUploaded ? t("list.view") : t("list.edit")}
        </Button>
        {!isUploaded && (
          <Button
            variant="ghost"
            size="sm"
            loading={busy}
            onClick={onDuplicate}
          >
            <Copy aria-hidden weight="bold" className="size-4" />
            {t("list.duplicate")}
          </Button>
        )}
        <Button variant="ghost" size="sm" disabled={busy} onClick={onDelete}>
          <Trash aria-hidden weight="bold" className="size-4" />
          {t("list.delete")}
        </Button>
      </div>
    </li>
  );
}
