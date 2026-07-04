"use client";

import { useTranslations } from "next-intl";
import { Archive, Copy, PencilSimple, Star } from "@phosphor-icons/react";
import { Button, StatusBadge, type StatusTone } from "@/components/ui";
import { formatDateTime } from "@/lib/format";
import type { CvSummary } from "@/lib/api";

const STATUS_TONE: Record<string, StatusTone> = {
  draft: "draft",
  ready: "active",
  archived: "closed",
};

export function CvLibraryCard({
  cv,
  locale,
  canCreate,
  limitHint,
  busy,
  onOpen,
  onDuplicate,
  onSetPrimary,
  onArchive,
}: {
  cv: CvSummary;
  locale: string;
  canCreate: boolean;
  limitHint?: string;
  busy: boolean;
  onOpen: () => void;
  onDuplicate: () => void;
  onSetPrimary: () => void;
  onArchive: () => void;
}) {
  const t = useTranslations("cv");

  return (
    <li className="marketplace-card marketplace-card-hover relative flex flex-col overflow-hidden rounded-[14px] p-4 pl-5 before:absolute before:inset-y-0 before:left-0 before:w-1 before:bg-[var(--brand-primary)] before:content-['']">
      <div className="flex items-start justify-between gap-2">
        <button
          type="button"
          onClick={onOpen}
          className="min-w-0 text-left outline-none focus-visible:underline"
        >
          <h3 className="truncate text-base font-bold text-[var(--text-primary)] hover:text-[var(--brand-primary)]">
            {cv.title}
          </h3>
        </button>
        {cv.is_primary && (
          <span
            className="flex shrink-0 items-center gap-1 rounded-full bg-[var(--amber-100)] px-2 py-0.5 text-xs font-semibold text-[var(--amber-700)]"
            title={t("list.primary")}
          >
            <Star aria-hidden weight="fill" className="size-3" />
            {t("list.primary")}
          </span>
        )}
      </div>

      <div className="mt-2 flex flex-wrap items-center gap-2">
        <StatusBadge tone={STATUS_TONE[cv.status] ?? "info"}>
          {cv.status_label}
        </StatusBadge>
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
          <PencilSimple aria-hidden weight="bold" className="size-4" />
          {t("list.edit")}
        </Button>
        <Button
          variant="ghost"
          size="sm"
          loading={busy}
          disabled={!canCreate}
          title={!canCreate ? limitHint : undefined}
          onClick={onDuplicate}
        >
          <Copy aria-hidden weight="bold" className="size-4" />
          {t("list.duplicate")}
        </Button>
        {!cv.is_primary && (
          <Button variant="ghost" size="sm" disabled={busy} onClick={onSetPrimary}>
            <Star aria-hidden weight="bold" className="size-4" />
            {t("list.setPrimary")}
          </Button>
        )}
        {cv.status !== "archived" && (
          <Button variant="ghost" size="sm" disabled={busy} onClick={onArchive}>
            <Archive aria-hidden weight="bold" className="size-4" />
            {t("list.archive")}
          </Button>
        )}
      </div>
    </li>
  );
}
