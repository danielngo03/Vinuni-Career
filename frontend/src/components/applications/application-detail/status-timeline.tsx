"use client";

import { useLocale, useTranslations } from "next-intl";
import { Check, ClockCounterClockwise } from "@phosphor-icons/react";
import { formatDateTime } from "@/lib/format";
import { useApplicationLabels } from "@/lib/applications/labels";
import type { ApplicationTimelineEvent } from "@/lib/api";

/** Contextual next-step hints derived from the current application status. */
export function statusNextSteps(status: string, t: (key: string) => string): string[] {
  switch (status) {
    case "submitted":
      return [t("nextStepsSubmitted0"), t("nextStepsSubmitted1"), t("nextStepsSubmitted2")];
    case "under_review":
      return [t("nextStepsUnderReview0"), t("nextStepsUnderReview1"), t("nextStepsUnderReview2")];
    case "rejected":
      return [t("nextStepsRejected0"), t("nextStepsRejected1"), t("nextStepsRejected2")];
    case "withdrawn":
      return [t("nextStepsWithdrawn0"), t("nextStepsWithdrawn1")];
    case "hired":
      return [t("nextStepsHired0"), t("nextStepsHired1")];
    default:
      return [];
  }
}

/**
 * Fallback ordered stages when the server timeline is absent (defensive-only —
 * stale cached data. The real backend always returns `timeline` now). Derived
 * from `status` alone, same as the pre-B-551 behavior.
 */
function fallbackTimelineSteps(status: string): string[] {
  if (status === "withdrawn") return ["submitted", "withdrawn"];
  if (status === "submitted") return ["submitted"];
  if (status === "under_review") return ["submitted", "under_review"];
  return ["submitted", "under_review", status];
}

function FallbackTimeline({
  status,
  statusLabel,
  lastStatusAt,
}: {
  status: string;
  statusLabel: string;
  lastStatusAt: string | null;
}) {
  const locale = useLocale();
  const labels = useApplicationLabels();
  const steps = fallbackTimelineSteps(status);
  const isNegative = status === "rejected" || status === "withdrawn";

  return (
    <ol className="flex flex-wrap items-start gap-y-3">
      {steps.map((code, i) => {
        const isCurrent = i === steps.length - 1;
        const currentColor = isNegative
          ? "var(--brand-red)"
          : "var(--brand-primary)";
        return (
          <li
            key={code}
            className="flex min-w-0 flex-1 basis-24 flex-col items-center text-center"
          >
            <div className="flex w-full items-center">
              <span
                className={
                  i === 0
                    ? "h-0.5 flex-1 bg-transparent"
                    : isCurrent && isNegative
                      ? "h-0.5 flex-1 bg-[var(--red-400)]/50"
                      : "h-0.5 flex-1 bg-[var(--brand-primary)]/40"
                }
                aria-hidden
              />
              <span
                className="flex size-6 shrink-0 items-center justify-center rounded-full border-2"
                style={{
                  borderColor: isCurrent ? currentColor : "var(--brand-primary)",
                  backgroundColor: isCurrent ? currentColor : "transparent",
                }}
                aria-hidden
              >
                {isCurrent ? (
                  <span className="size-2 rounded-full bg-white" />
                ) : (
                  <Check
                    weight="bold"
                    className="size-3.5 text-[var(--brand-primary)]"
                  />
                )}
              </span>
              <span
                className={
                  i === steps.length - 1
                    ? "h-0.5 flex-1 bg-transparent"
                    : "h-0.5 flex-1 bg-[var(--brand-primary)]/40"
                }
                aria-hidden
              />
            </div>
            <span
              className={
                isCurrent
                  ? "mt-1.5 px-1 text-xs font-semibold text-[var(--text-primary)]"
                  : "mt-1.5 px-1 text-xs font-medium text-[var(--text-secondary)]"
              }
            >
              {isCurrent ? labels.status(code, statusLabel) : labels.status(code)}
            </span>
            {isCurrent && lastStatusAt && (
              <span className="mt-0.5 px-1 text-[11px] text-[var(--text-muted)]">
                {formatDateTime(lastStatusAt, locale)}
              </span>
            )}
          </li>
        );
      })}
    </ol>
  );
}

/**
 * Real, server-sourced event log rendered as a vertical narrative — replaces
 * the earlier client-side guess derived from `status` alone. Each entry is
 * `{event_type, label, occurred_at}`; `label` is already locale-resolved
 * server-side and must never be re-translated here.
 */
function EventTimeline({ events }: { events: ApplicationTimelineEvent[] }) {
  const locale = useLocale();
  const lastIdx = events.length - 1;

  return (
    <ol className="space-y-0">
      {events.map((event, i) => {
        const isCurrent = i === lastIdx;
        return (
          <li key={`${event.event_type}-${event.occurred_at}-${i}`} className="flex gap-3">
            <div className="flex flex-col items-center">
              <span
                className="flex size-6 shrink-0 items-center justify-center rounded-full border-2"
                style={{
                  borderColor: "var(--brand-primary)",
                  backgroundColor: isCurrent ? "var(--brand-primary)" : "transparent",
                }}
                aria-hidden
              >
                {isCurrent ? (
                  <span className="size-2 rounded-full bg-white" />
                ) : (
                  <Check weight="bold" className="size-3.5 text-[var(--brand-primary)]" />
                )}
              </span>
              {i !== lastIdx && (
                <span className="w-0.5 flex-1 bg-[var(--brand-primary)]/30" aria-hidden />
              )}
            </div>
            <div className={i !== lastIdx ? "pb-4" : ""}>
              <p
                className={
                  isCurrent
                    ? "text-sm font-semibold text-[var(--text-primary)]"
                    : "text-sm font-medium text-[var(--text-secondary)]"
                }
              >
                {event.label}
              </p>
              {event.occurred_at && (
                <p className="mt-0.5 text-xs text-[var(--text-muted)]">
                  {formatDateTime(event.occurred_at, locale)}
                </p>
              )}
            </div>
          </li>
        );
      })}
    </ol>
  );
}

export function StatusTimeline({
  status,
  statusLabel,
  lastStatusAt,
  timeline,
}: {
  status: string;
  statusLabel: string;
  lastStatusAt: string | null;
  /** Real server timeline (ordered ascending). Optional/defensive fallback only. */
  timeline?: ApplicationTimelineEvent[];
}) {
  const t = useTranslations("applications");
  const hasRealTimeline = Boolean(timeline && timeline.length > 0);

  return (
    <section className="mb-6 rounded-2xl border border-[var(--glass-border)] bg-[var(--glass-surface)] backdrop-blur-md p-4">
      <h2 className="mb-3 flex items-center gap-2 text-sm font-bold text-[var(--text-primary)]">
        <ClockCounterClockwise aria-hidden weight="duotone" className="size-4 text-[var(--text-muted)]" />
        {t("statusTimelineTitle")}
      </h2>
      {hasRealTimeline ? (
        <EventTimeline events={timeline as ApplicationTimelineEvent[]} />
      ) : (
        <FallbackTimeline status={status} statusLabel={statusLabel} lastStatusAt={lastStatusAt} />
      )}
    </section>
  );
}
