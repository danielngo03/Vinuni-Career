"use client";

import { useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import { useMutation } from "@tanstack/react-query";
import {
  CalendarCheck,
  MapPin,
  SealCheck,
  ShieldWarning,
  VideoCamera,
} from "@phosphor-icons/react";
import { Button, Modal, StatusBadge, Textarea, useToast } from "@/components/ui";
import { formatDateTime } from "@/lib/format";
import { INTERVIEW_STATUS_TONE, useInterviewLabels } from "@/lib/applications/labels";
import {
  ApiError,
  applicationsApi,
  type InterviewRespondAction,
  type StudentInterviewCard as StudentInterviewCardData,
} from "@/lib/api";
import { useApiErrorMessage } from "@/lib/auth/use-api-error";
import { Meta } from "./meta";

/**
 * The candidate's own upcoming-interview card. The student is an attendee, so
 * date/mode + their location-or-link is shown. This is the ONLY interview surface
 * the student sees — it carries NO assignee identities, NO scores, NO gate.
 *
 * Theme D: the student can Confirm / Decline / Request-reschedule a still-
 * scheduled interview. Confirm is low-stakes (direct); decline / reschedule open
 * a confirm modal with an optional note. Once responded, the recorded state is
 * shown and the actions are replaced.
 */
export function UpcomingInterviewCard({
  interview,
  applicationId,
  onResponded,
}: {
  interview: StudentInterviewCardData;
  applicationId: string;
  onResponded: () => void;
}) {
  const t = useTranslations("applications");
  const tc = useTranslations("common");
  const locale = useLocale();
  const labels = useInterviewLabels();
  const toast = useToast();
  const apiError = useApiErrorMessage();

  const [confirm, setConfirm] = useState<"decline" | "request_reschedule" | null>(
    null,
  );
  const [note, setNote] = useState("");

  const isOnline = interview.mode === "online";
  const isOnsite = interview.mode === "onsite";
  const ModeIcon = isOnline ? VideoCamera : isOnsite ? MapPin : CalendarCheck;

  const responded = interview.candidate_response != null;
  const actionable = interview.status === "scheduled" && !responded;

  const respond = useMutation({
    mutationFn: (action: InterviewRespondAction) =>
      applicationsApi.respondToInterview(
        applicationId,
        interview.id,
        action,
        action === "confirm" ? undefined : note.trim() || undefined,
      ),
    onSuccess: (_res, action) => {
      setConfirm(null);
      setNote("");
      toast.show({
        tone: action === "confirm" ? "success" : "info",
        title:
          action === "confirm"
            ? t("interviewConfirmedToast")
            : action === "decline"
              ? t("interviewDeclinedToast")
              : t("interviewRescheduleToast"),
      });
      onResponded();
    },
    onError: (e) => {
      setConfirm(null);
      // The interview changed state (cancelled / passed) or was already
      // responded between render and click → friendly state, then refresh.
      if (
        e instanceof ApiError &&
        e.isConflict &&
        (e.details?.reason === "interview_not_respondable" ||
          e.details?.reason === "interview_response_conflict")
      ) {
        toast.show({ tone: "warning", title: t("interviewNotRespondableToast") });
        onResponded();
        return;
      }
      toast.show({ tone: "error", title: apiError(e) });
    },
  });

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

      {/* Response region (Theme D). */}
      {responded ? (
        <p
          className={
            interview.candidate_response === "confirmed"
              ? "mt-4 flex items-center gap-2 text-sm font-semibold text-[var(--teal-600)]"
              : "mt-4 flex items-center gap-2 text-sm text-[var(--text-muted)]"
          }
        >
          {interview.candidate_response === "confirmed" ? (
            <SealCheck aria-hidden weight="duotone" className="size-4" />
          ) : (
            <ShieldWarning aria-hidden weight="duotone" className="size-4" />
          )}
          {t("interviewYourResponse", {
            response: interview.candidate_response_label ?? "",
          })}
        </p>
      ) : actionable ? (
        <div className="mt-4 flex flex-wrap gap-2">
          <Button
            variant="primary"
            onClick={() => respond.mutate("confirm")}
            loading={respond.isPending && !confirm}
            disabled={respond.isPending}
          >
            <SealCheck aria-hidden weight="bold" className="size-4" />
            {t("interviewConfirm")}
          </Button>
          <Button
            variant="secondary"
            onClick={() => {
              setNote("");
              setConfirm("request_reschedule");
            }}
            disabled={respond.isPending}
          >
            {t("interviewReschedule")}
          </Button>
          <Button
            variant="ghost"
            onClick={() => {
              setNote("");
              setConfirm("decline");
            }}
            disabled={respond.isPending}
          >
            {t("interviewDecline")}
          </Button>
        </div>
      ) : null}

      {/* Decline / reschedule confirm modal with an optional note. */}
      <Modal
        open={!!confirm}
        onClose={respond.isPending ? () => {} : () => setConfirm(null)}
        title={
          confirm === "decline"
            ? t("interviewDeclineConfirmTitle")
            : t("interviewRescheduleConfirmTitle")
        }
        description={
          confirm === "decline"
            ? t("interviewDeclineConfirmBody")
            : t("interviewRescheduleConfirmBody")
        }
        size="sm"
        closeLabel={tc("close")}
        footer={
          <>
            <Button
              variant="ghost"
              onClick={() => setConfirm(null)}
              disabled={respond.isPending}
            >
              {tc("cancel")}
            </Button>
            <Button
              variant={confirm === "decline" ? "danger" : "primary"}
              loading={respond.isPending}
              onClick={() => confirm && respond.mutate(confirm)}
            >
              {confirm === "decline"
                ? t("interviewDeclineConfirm")
                : t("interviewRescheduleConfirm")}
            </Button>
          </>
        }
      >
        <Textarea
          label={t("interviewRespondNoteLabel")}
          rows={3}
          maxLength={2000}
          value={note}
          placeholder={t("interviewRespondNotePlaceholder")}
          help={t("interviewRespondNoteHelp")}
          onChange={(e) => setNote(e.target.value)}
        />
      </Modal>
    </section>
  );
}
