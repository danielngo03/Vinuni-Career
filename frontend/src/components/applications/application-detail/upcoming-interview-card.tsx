"use client";

import { useLocale, useTranslations } from "next-intl";
import { CalendarCheck, MapPin, VideoCamera } from "@phosphor-icons/react";
import { StatusBadge } from "@/components/ui";
import { formatDateTime } from "@/lib/format";
import { INTERVIEW_STATUS_TONE, useInterviewLabels } from "@/lib/applications/labels";
import type { StudentInterviewCard as StudentInterviewCardData } from "@/lib/api";
import { Meta } from "./meta";

/**
 * The candidate's own upcoming-interview card. The student is an attendee, so
 * date/mode + their location-or-link is shown. This is the ONLY interview surface
 * the student sees — it carries NO assignee identities, NO scores, NO gate.
 */
export function UpcomingInterviewCard({
  interview,
}: {
  interview: StudentInterviewCardData;
}) {
  const t = useTranslations("applications");
  const locale = useLocale();
  const labels = useInterviewLabels();

  const isOnline = interview.mode === "online";
  const isOnsite = interview.mode === "onsite";
  const ModeIcon = isOnline ? VideoCamera : isOnsite ? MapPin : CalendarCheck;

  return (
    <section className="mb-6 rounded-2xl border border-[var(--glass-border)] bg-[var(--glass-surface)] p-4 shadow-[0_2px_16px_rgba(11,34,57,0.07)] backdrop-blur-xl">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h2 className="inline-flex items-center gap-2 text-sm font-bold text-[var(--text-primary)]">
          <span className="flex size-7 shrink-0 items-center justify-center rounded-lg icon-chip-primary shadow-sm">
            <CalendarCheck
              aria-hidden
              weight="duotone"
              className="size-4 text-white"
            />
          </span>
          {t("interviewTitle")}
        </h2>
        <StatusBadge tone={INTERVIEW_STATUS_TONE[interview.status] ?? "info"}>
          {labels.status(interview.status)}
        </StatusBadge>
      </div>

      <dl className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2">
        <Meta label={t("interviewWhen")}>
          {formatDateTime(interview.scheduled_at, locale)}
        </Meta>
        <Meta label={t("interviewMode")}>
          <span className="inline-flex items-center gap-1.5">
            <ModeIcon
              aria-hidden
              weight="duotone"
              className="size-4 text-[var(--text-muted)]"
            />
            {labels.mode(interview.mode, interview.mode_label)}
          </span>
        </Meta>
        <Meta label={t("interviewDuration")}>
          {t("interviewDurationValue", { minutes: interview.duration_minutes })}
        </Meta>
        <Meta
          label={
            isOnline
              ? t("interviewLink")
              : isOnsite
                ? t("interviewLocation")
                : t("interviewContact")
          }
        >
          {interview.location_or_link ? (
            isOnline ? (
              <a
                href={interview.location_or_link}
                target="_blank"
                rel="noopener noreferrer"
                className="break-all rounded text-[var(--brand-primary)] underline outline-none hover:opacity-80 focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)]/30"
              >
                {interview.location_or_link}
              </a>
            ) : (
              <span className="break-words">{interview.location_or_link}</span>
            )
          ) : (
            <span className="text-[var(--text-secondary)]">
              {t("interviewPhoneNote")}
            </span>
          )}
        </Meta>
      </dl>
    </section>
  );
}
