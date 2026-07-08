"use client";

import { useLocale, useTranslations } from "next-intl";
import {
  ArrowCounterClockwise,
  ClockCounterClockwise,
  GitCommit,
} from "@phosphor-icons/react";
import { Button } from "@/components/ui";
import { formatDateTime } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { CvVersionSummary } from "@/lib/api";

/**
 * Version history timeline (design spec §3 "Phiên bản / Versions"). Each accepted
 * edit creates an immutable `cv_versions` snapshot (CV_STUDIO_SPEC §4). Renders a
 * proper timeline — timestamp + change summary + a current-version marker + a
 * Restore action on any non-current snapshot (`cvApi.restoreVersion`,
 * non-destructive). Replaces the scattered version cards.
 */
export function VersionsPanel({
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
  const t = useTranslations("cv.versions");
  const locale = useLocale();
  const rows = versions ?? [];

  return (
    <section
      aria-label={t("title")}
      className="rounded-2xl border border-[var(--glass-border-strong)] bg-[var(--glass-surface)] p-5 shadow-[var(--shadow-sm)] backdrop-blur-md"
    >
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2.5">
          <span className="flex size-6 shrink-0 items-center justify-center rounded-lg icon-chip-neutral shadow-sm">
            <ClockCounterClockwise aria-hidden weight="duotone" className="size-3.5 text-white" />
          </span>
          <h3 className="text-sm font-bold text-[var(--text-primary)]">{t("title")}</h3>
        </div>
        <span className="rounded-full bg-[var(--glass-surface-light)] px-2 py-0.5 text-[11px] font-semibold tabular-nums text-[var(--text-secondary)]">
          v{version}
        </span>
      </div>

      {rows.length > 0 ? (
        <ol className="mt-4 space-y-0">
          {rows.map((v, i) => {
            const isLast = i === rows.length - 1;
            const restoring = restoringId === v.id;
            return (
              <li key={v.id} className="relative flex gap-3 pb-4 last:pb-0">
                {/* Timeline rail */}
                <div className="flex flex-col items-center">
                  <span
                    aria-hidden
                    className={cn(
                      "mt-0.5 flex size-6 shrink-0 items-center justify-center rounded-full border-2",
                      v.is_current
                        ? "border-[var(--brand-teal)] bg-[var(--teal-50)] text-[var(--teal-600)]"
                        : "border-[var(--glass-border-strong)] bg-[var(--glass-surface-light)] text-[var(--text-muted)]",
                    )}
                  >
                    <GitCommit weight="bold" className="size-3" />
                  </span>
                  {!isLast && <span aria-hidden className="mt-1 w-px flex-1 bg-[var(--glass-border-strong)]" />}
                </div>

                {/* Entry */}
                <div className="min-w-0 flex-1 pt-0.5">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-sm font-semibold text-[var(--text-primary)]">v{v.version}</span>
                    {v.is_current && (
                      <span className="rounded-full bg-[var(--teal-50)] px-1.5 py-0.5 text-[10px] font-semibold text-[var(--teal-600)]">
                        {t("currentTag")}
                      </span>
                    )}
                    {v.change_source && v.change_source !== "manual" && t.has(`source.${v.change_source}`) && (
                      <span className="rounded-full bg-[var(--glass-surface-light)] px-1.5 py-0.5 text-[10px] font-medium text-[var(--text-muted)]">
                        {t(`source.${v.change_source}`)}
                      </span>
                    )}
                    {onRestore && !v.is_current && (
                      <Button
                        variant="ghost"
                        size="sm"
                        className="ml-auto"
                        loading={restoring}
                        onClick={() => onRestore(v.id)}
                      >
                        <ArrowCounterClockwise aria-hidden weight="bold" className="size-3.5" />
                        {t("restore")}
                      </Button>
                    )}
                  </div>
                  {v.change_summary && (
                    <p className="mt-0.5 text-xs leading-relaxed text-[var(--text-secondary)]">
                      {v.change_summary}
                    </p>
                  )}
                  <p className="mt-0.5 text-[11px] text-[var(--text-muted)]">
                    {formatDateTime(v.created_at ?? (v.is_current ? lastEditedAt : null), locale)}
                  </p>
                </div>
              </li>
            );
          })}
        </ol>
      ) : (
        <div className="mt-4 rounded-xl border border-dashed border-[var(--glass-border-strong)] bg-[var(--glass-surface-light)] px-4 py-5 text-center">
          <p className="text-xs leading-relaxed text-[var(--text-muted)]">{t("note")}</p>
          {lastEditedAt && (
            <p className="mt-1.5 text-[11px] text-[var(--text-muted)]">
              {t("lastEdited")}: {formatDateTime(lastEditedAt, locale)}
            </p>
          )}
        </div>
      )}
    </section>
  );
}
