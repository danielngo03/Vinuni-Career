"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { CaretDown, ChartLineUp } from "@phosphor-icons/react";
import { cn } from "@/lib/utils";
import type { CvSection } from "@/lib/api";
import { DocumentHealthCard } from "./document-health-card";
import { CvJobFitRail } from "../cv-job-fit-rail";

/**
 * Insights strip (design spec §3 "relocate DocumentHealthCard / CvJobFitRail
 * cleanly"). A single collapsible container that groups the document-health
 * hints and the job-fit rail so they no longer scatter across the inspector.
 * Collapsed by default on the desktop inspector to keep the AI/design tabs the
 * focus; expandable on demand.
 */
export function InsightsPanel({
  cvId,
  jobId,
  sections,
  defaultOpen = false,
}: {
  cvId: string;
  jobId?: string | null;
  sections: CvSection[];
  defaultOpen?: boolean;
}) {
  const t = useTranslations("cv.insights");
  const [open, setOpen] = useState(defaultOpen);

  return (
    <section
      aria-label={t("title")}
      className="rounded-2xl border border-[var(--glass-border-strong)] bg-[var(--glass-surface)] shadow-[var(--shadow-sm)] backdrop-blur-md"
    >
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-2.5 rounded-2xl px-4 py-3 text-left outline-none transition-colors hover:bg-[var(--glass-surface-light)] focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/30"
      >
        <span className="flex size-6 shrink-0 items-center justify-center rounded-lg icon-chip-primary shadow-sm">
          <ChartLineUp aria-hidden weight="duotone" className="size-3.5 text-white" />
        </span>
        <span className="min-w-0 flex-1">
          <span className="block text-sm font-bold text-[var(--text-primary)]">{t("title")}</span>
          <span className="block text-xs text-[var(--text-muted)]">{t("subtitle")}</span>
        </span>
        <CaretDown
          aria-hidden
          weight="bold"
          className={cn("size-4 shrink-0 text-[var(--text-muted)] transition-transform", open && "rotate-180")}
        />
      </button>

      {open && (
        <div className="space-y-4 border-t border-[var(--glass-border)] p-4">
          <DocumentHealthCard sections={sections} />
          <CvJobFitRail cvId={cvId} jobId={jobId} />
        </div>
      )}
    </section>
  );
}
