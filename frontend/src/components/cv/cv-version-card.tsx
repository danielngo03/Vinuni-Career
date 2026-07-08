"use client";

import { useLocale, useTranslations } from "next-intl";
import { ArrowCounterClockwise, ClockCounterClockwise } from "@phosphor-icons/react";
import { Button } from "@/components/ui";
import { formatDateTime } from "@/lib/format";
import type { CvVersionSummary } from "@/lib/api";

/**
 * Version history. Each accepted section edit creates a new immutable
 * `cv_versions` snapshot (CV_STUDIO_SPEC §4). The list is fed from
 * `GET /cvs/{id}` (`versions[]`) / `GET /cvs/{id}/versions`; the head entry is
 * the current snapshot. Non-current snapshots can be restored (non-destructive).
 */
export function CvVersionCard({
  version,
  lastEditedAt,
  versions,
  onRestore,
  restoringId,
}: {
  version: number;
  lastEditedAt: string | null;
  versions?: CvVersionSummary[];
  onRestore?: (versionId: string) => void;
  restoringId?: string | null;
}) {
  const t = useTranslations("cv");
  const locale = useLocale();

  return (
    <section
      aria-label={t("versions.title")}
      className="rounded-2xl border border-[var(--glass-border-strong)] bg-[var(--glass-surface)] p-5 shadow-[0_2px_12px_rgba(11,34,57,0.06)] backdrop-blur-md"
    >
      <div className="flex items-center gap-2.5">
        <span className="flex size-6 shrink-0 items-center justify-center rounded-lg icon-chip-neutral shadow-sm">
          <ClockCounterClockwise aria-hidden weight="duotone" className="size-3.5 text-white" />
        </span>
        <h3 className="text-sm font-bold text-[var(--text-primary)]">
          {t("versions.title")}
        </h3>
      </div>

      <dl className="mt-3 space-y-1 text-sm">
        <div className="flex items-center justify-between">
          <dt className="text-[var(--text-secondary)]">
            {t("versions.current")}
          </dt>
          <dd className="font-semibold text-[var(--text-primary)]">
            v{version}
          </dd>
        </div>
        <div className="flex items-center justify-between">
          <dt className="text-[var(--text-secondary)]">
            {t("versions.lastEdited")}
          </dt>
          <dd className="text-[var(--text-primary)]">
            {formatDateTime(lastEditedAt, locale)}
          </dd>
        </div>
      </dl>

      {versions && versions.length > 0 ? (
        <ol className="mt-3 divide-y divide-[var(--glass-border)] rounded-xl border border-[var(--glass-border-strong)]">
          {versions.map((v) => (
            <li
              key={v.id}
              className="flex items-center justify-between gap-3 px-3 py-2 text-sm"
            >
              <span className="flex min-w-0 items-center gap-2">
                <span className="font-medium text-[var(--text-primary)]">
                  v{v.version}
                </span>
                {v.is_current && (
                  <span className="rounded-full bg-[var(--teal-50)] px-1.5 py-0.5 text-[10px] font-semibold text-[var(--teal-600)]">
                    {t("versions.currentTag")}
                  </span>
                )}
                <span className="truncate text-xs text-[var(--text-secondary)]">
                  {v.change_summary ?? formatDateTime(v.created_at ?? null, locale)}
                </span>
              </span>
              {onRestore && !v.is_current && (
                <Button
                  variant="ghost"
                  size="sm"
                  loading={restoringId === v.id}
                  onClick={() => onRestore(v.id)}
                >
                  <ArrowCounterClockwise
                    aria-hidden
                    weight="bold"
                    className="size-3.5"
                  />
                  {t("versions.restore")}
                </Button>
              )}
            </li>
          ))}
        </ol>
      ) : (
        <p className="mt-3 text-xs text-[var(--text-muted)]">
          {t("versions.note")}
        </p>
      )}
    </section>
  );
}
