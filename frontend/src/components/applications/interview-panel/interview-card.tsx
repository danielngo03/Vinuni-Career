"use client";

import { useTranslations } from "next-intl";
import {
  CheckCircle2,
  MapPin,
  Pencil,
  Ban,
  UserRound,
  Users,
  Video,
} from "lucide-react";
import { Button } from "@/components/ui";
import { StatusChip } from "@/components/kit";
import { formatDateTime } from "@/lib/format";
import { useInterviewLabels } from "@/lib/applications/labels";
import { INTERVIEW_STATUS_CHIP } from "../chip-tones";
import type { Interview } from "@/lib/api";

export function InterviewCard({
  interview,
  locale,
  canManage,
  onEdit,
  onCancel,
  onComplete,
  onAssignees,
}: {
  interview: Interview;
  locale: string;
  canManage: boolean;
  onEdit: () => void;
  onCancel: () => void;
  onComplete: () => void;
  onAssignees: () => void;
}) {
  const t = useTranslations("interviews");
  const labels = useInterviewLabels();
  const isOpen = interview.status === "scheduled";
  const ev = interview.evaluation;

  const ModeIcon =
    interview.mode === "online" ? Video : interview.mode === "onsite" ? MapPin : Users;

  return (
    <div className="rounded-lg border border-border bg-card p-3.5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="inline-flex items-center gap-1.5 type-small font-semibold text-foreground">
          <ModeIcon aria-hidden className="size-4 text-muted-foreground" strokeWidth={1.8} />
          {labels.mode(interview.mode, interview.mode_label)}
        </span>
        <StatusChip tone={INTERVIEW_STATUS_CHIP[interview.status] ?? "neutral"}>
          {labels.status(interview.status)}
        </StatusChip>
      </div>

      {interview.title && (
        <p className="mt-1.5 type-small font-medium text-foreground">{interview.title}</p>
      )}

      <dl className="mt-2 space-y-1 type-small">
        <div className="flex flex-wrap items-baseline gap-x-2">
          <dt className="type-caption text-muted-foreground">{t("whenLabel")}</dt>
          <dd className="text-foreground">
            {formatDateTime(interview.scheduled_at, locale)}
            {" · "}
            {t("durationValue", { minutes: interview.duration_minutes })}
          </dd>
        </div>

        {interview.location && (
          <div className="flex flex-wrap items-baseline gap-x-2">
            <dt className="type-caption text-muted-foreground">{t("locationLabel")}</dt>
            <dd className="text-muted-foreground">{interview.location}</dd>
          </div>
        )}

        {/* meeting_link is ATTENDEE-ONLY: render only when the API returns it. */}
        {interview.meeting_link && (
          <div className="flex flex-wrap items-baseline gap-x-2">
            <dt className="type-caption text-muted-foreground">{t("linkLabel")}</dt>
            <dd className="min-w-0 break-all">
              <a
                href={interview.meeting_link}
                target="_blank"
                rel="noopener noreferrer"
                className="rounded text-[var(--brand-primary)] underline outline-none hover:opacity-80 focus-visible:ring-2 focus-visible:ring-[var(--field-focus-border)]"
              >
                {interview.meeting_link}
              </a>
            </dd>
          </div>
        )}
      </dl>

      {/* Assignees (partner-org members; never the student). */}
      <div className="mt-2.5">
        <p className="type-caption text-muted-foreground">{t("assigneesLabel")}</p>
        {interview.assignees.length === 0 ? (
          <p className="mt-0.5 type-caption text-muted-foreground">{t("noAssignees")}</p>
        ) : (
          <ul className="mt-1 flex flex-wrap gap-1.5">
            {interview.assignees.map((a) => (
              <li
                key={a.user_id}
                className="inline-flex items-center gap-1 rounded-full border border-border bg-[var(--bg-subtle)] px-2 py-0.5 type-caption font-medium text-muted-foreground"
              >
                <UserRound aria-hidden className="size-3" strokeWidth={1.8} />
                {a.name?.trim() || t("assigneeFallback")}
              </li>
            ))}
          </ul>
        )}
      </div>

      {/* Extended gate state for the interview's stage (partner-only). */}
      {ev && ev.required > 0 && (
        <div className="mt-2.5 flex flex-wrap items-center gap-2 border-t border-border pt-2.5">
          <span className="type-caption font-medium text-muted-foreground">
            {t("gateScorecards", { submitted: ev.submitted_count, required: ev.required })}
          </span>
          {ev.avg_overall != null && (
            <span className="type-caption font-medium text-muted-foreground">
              {ev.threshold != null
                ? t("gateAvgThreshold", {
                    avg: ev.avg_overall.toFixed(1),
                    threshold: ev.threshold.toFixed(1),
                  })
                : t("gateAvg", { avg: ev.avg_overall.toFixed(1) })}
            </span>
          )}
          <StatusChip tone={ev.gate_met ? "success" : "warning"}>
            {ev.gate_met ? t("gateMet") : t("gateBlocked")}
          </StatusChip>
        </div>
      )}

      {/* Manage actions (only on the open interview). */}
      {canManage && isOpen && (
        <div className="mt-3 flex flex-wrap gap-1.5">
          <Button variant="secondary" size="sm" onClick={onEdit}>
            <Pencil aria-hidden className="size-4" strokeWidth={1.8} />
            {t("reschedule")}
          </Button>
          <Button variant="ghost" size="sm" onClick={onAssignees}>
            <Users aria-hidden className="size-4" strokeWidth={1.8} />
            {t("editAssignees")}
          </Button>
          <Button variant="ghost" size="sm" onClick={onComplete}>
            <CheckCircle2 aria-hidden className="size-4" strokeWidth={1.8} />
            {t("complete")}
          </Button>
          <Button variant="ghost" size="sm" onClick={onCancel}>
            <Ban aria-hidden className="size-4" strokeWidth={1.8} />
            {t("cancel")}
          </Button>
        </div>
      )}
    </div>
  );
}
