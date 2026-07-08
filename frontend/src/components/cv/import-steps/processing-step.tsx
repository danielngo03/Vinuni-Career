"use client";

import { useTranslations } from "next-intl";
import { ArrowsClockwise, CheckCircle, Circle, Sparkle } from "@phosphor-icons/react";
import { cn } from "@/lib/utils";
import { INGESTION_PROGRESS_STEPS, type Ingestion } from "@/lib/api";

/** Step: processing (ingestion in progress). */
export function ProcessingStep({
  ingestion,
  seenScanned,
}: {
  ingestion: Ingestion | null;
  seenScanned: boolean;
}) {
  const t = useTranslations("cv.import");
  const tStep = useTranslations("cv.import.steps");
  const status = ingestion?.status ?? "queued";

  const steps = INGESTION_PROGRESS_STEPS.filter(
    (s) => s !== "reading_scanned" || seenScanned || status === "reading_scanned",
  );
  const currentIdx = steps.indexOf(status as (typeof steps)[number]);

  return (
    <div className="mx-auto max-w-md py-8">
      <div className="rounded-2xl border border-[var(--ai-accent)]/25 bg-gradient-to-br from-[var(--ai-accent-soft)] to-[var(--glass-surface-light)] p-6 text-center backdrop-blur-xl">
        <div className="mb-4 flex items-center justify-center">
          <div className="relative flex size-14 items-center justify-center">
            <span
              aria-hidden
              className="absolute inset-0 animate-spin rounded-full border-[3px] border-[var(--ai-accent)]/30 border-t-[var(--ai-accent)]"
            />
            <Sparkle aria-hidden weight="duotone" className="size-6 text-[var(--ai-accent)]" />
          </div>
        </div>
        <p
          role="status"
          aria-live="polite"
          className="text-base font-bold text-[var(--text-primary)]"
        >
          {ingestion?.status_label ?? t("preparing")}
        </p>
        <p className="mt-1.5 text-xs text-[var(--text-muted)]">{t("processingHint")}</p>
      </div>

      <ol className="mt-7 space-y-2.5">
        {steps.map((s, i) => {
          const done = currentIdx > i;
          const active = currentIdx === i || (currentIdx < 0 && i === 0);
          return (
            <li key={s} className="flex items-center gap-2.5">
              {done ? (
                <CheckCircle aria-hidden weight="fill" className="size-5 text-[var(--brand-teal)]" />
              ) : active ? (
                <ArrowsClockwise
                  aria-hidden
                  weight="bold"
                  className="size-5 animate-spin text-[var(--brand-primary)]"
                />
              ) : (
                <Circle aria-hidden weight="bold" className="size-5 text-[var(--gray-300)]" />
              )}
              <span
                className={cn(
                  "text-sm",
                  done
                    ? "font-medium text-[var(--text-secondary)]"
                    : active
                      ? "font-semibold text-[var(--text-primary)]"
                      : "text-[var(--text-muted)]",
                )}
              >
                {tStep(s)}
              </span>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
