"use client";

import { useMemo, useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarPlus, WarningCircle } from "@phosphor-icons/react";
import { Button, useToast } from "@/components/ui";
import { ApiError, applicationsApi, type Interview } from "@/lib/api";
import { useApiErrorMessage } from "@/lib/auth/use-api-error";
import { RevealBlocked } from "./interview-panel/reveal-blocked";
import { InterviewCard } from "./interview-panel/interview-card";
import { InterviewFormModal } from "./interview-panel/interview-form-modal";
import { AssigneesModal } from "./interview-panel/assignees-modal";
import { CompleteModal } from "./interview-panel/complete-modal";
import { ActionModal } from "./interview-panel/action-modal";

/**
 * Partner-internal interview scheduling + management (ADR-0006). Lives inside the
 * partner candidate detail Sheet (alongside the scorecard panel). NEVER rendered
 * on any student surface — the student sees only their own upcoming-interview card.
 *
 * Reveal precondition (ADR-0006 §3): scheduling an interview on an anonymous
 * application requires an already-accepted reveal. When the candidate is still
 * anonymous + unrevealed the form is replaced by a blocked state that deep-links
 * the reveal flow; a `409 reveal_required` from the API is handled the same way.
 */
export function PartnerInterviewPanel({
  applicationId,
  canSchedule,
  anonUnrevealed,
  revealPending,
  onRequestReveal,
}: {
  applicationId: string;
  /** Scheduling is only valid while the candidate is actively under review. */
  canSchedule: boolean;
  /** True while the applicant is anonymous and the reveal is not yet accepted. */
  anonUnrevealed: boolean;
  /** True when a reveal request is already pending the student's response. */
  revealPending: boolean;
  /** Opens the existing reveal-request flow (deep-link from the blocked state). */
  onRequestReveal: () => void;
}) {
  const t = useTranslations("interviews");
  const tc = useTranslations("common");
  const locale = useLocale();
  const toast = useToast();
  const qc = useQueryClient();
  const apiError = useApiErrorMessage();

  const listKey = useMemo(
    () => ["applications", "interviews", applicationId] as const,
    [applicationId],
  );

  const query = useQuery({
    queryKey: listKey,
    queryFn: () => applicationsApi.listInterviews(applicationId),
    retry: false,
  });

  const interviews = query.data?.interviews ?? [];
  const hasOpen = interviews.some((iv) => iv.status === "scheduled");

  /* ----------------------------- modal state ----------------------------- */
  const [scheduleOpen, setScheduleOpen] = useState(false);
  const [editTarget, setEditTarget] = useState<Interview | null>(null);
  const [cancelTarget, setCancelTarget] = useState<Interview | null>(null);
  const [completeTarget, setCompleteTarget] = useState<Interview | null>(null);
  const [assigneeTarget, setAssigneeTarget] = useState<Interview | null>(null);

  function invalidate() {
    void qc.invalidateQueries({ queryKey: listKey });
    void qc.invalidateQueries({
      queryKey: ["applications", "partnerDetail", applicationId],
    });
    void qc.invalidateQueries({ queryKey: ["applications", "pipeline"] });
  }

  /* ------------------------------- header -------------------------------- */
  const header = (
    <div className="flex items-center justify-between gap-2">
      <div className="flex items-center gap-2">
        <span className="flex size-7 shrink-0 items-center justify-center rounded-lg icon-chip-success shadow-sm">
          <CalendarPlus aria-hidden weight="duotone" className="size-4 text-white" />
        </span>
        <h3 className="text-base font-bold text-[var(--text-primary)]">
          {t("panelTitle")}
        </h3>
      </div>
      <span className="text-xs font-medium text-[var(--text-muted)]">
        {t("partnerOnly")}
      </span>
    </div>
  );

  if (query.isPending) {
    return (
      <section aria-label={t("panelTitle")} className="space-y-3">
        {header}
        <div
          className="h-24 animate-pulse rounded-xl bg-[var(--bg-muted)]"
          aria-hidden
        />
      </section>
    );
  }

  if (query.isError) {
    const permission =
      query.error instanceof ApiError && query.error.isPermissionError;
    return (
      <section aria-label={t("panelTitle")} className="space-y-3">
        {header}
        <div className="rounded-xl border border-[var(--border-default)] bg-white p-3.5 ">
          <p className="flex items-center gap-2 text-sm text-[var(--text-secondary)]">
            <WarningCircle
              aria-hidden
              weight="duotone"
              className="size-4 text-[var(--text-muted)]"
            />
            {permission ? t("noPermission") : t("loadError")}
          </p>
          {!permission && (
            <Button
              variant="secondary"
              size="sm"
              className="mt-2"
              onClick={() => query.refetch()}
            >
              {tc("retry")}
            </Button>
          )}
        </div>
      </section>
    );
  }

  const showScheduleButton = canSchedule && !hasOpen;

  return (
    <section aria-label={t("panelTitle")} className="space-y-3">
      {header}

      {/* Reveal precondition: scheduling needs an accepted reveal first. */}
      {anonUnrevealed ? (
        <RevealBlocked
          pending={revealPending}
          onRequestReveal={onRequestReveal}
        />
      ) : null}

      {/* Existing interviews. */}
      {interviews.length === 0 ? (
        !anonUnrevealed && (
          <div className="rounded-xl border border-[var(--border-default)] bg-white p-3.5 ">
            <p className="text-sm text-[var(--text-secondary)]">
              {t("emptyBody")}
            </p>
          </div>
        )
      ) : (
        <ul className="space-y-2.5">
          {interviews.map((iv) => (
            <li key={iv.id}>
              <InterviewCard
                interview={iv}
                locale={locale}
                canManage={canSchedule}
                onEdit={() => setEditTarget(iv)}
                onCancel={() => setCancelTarget(iv)}
                onComplete={() => setCompleteTarget(iv)}
                onAssignees={() => setAssigneeTarget(iv)}
              />
            </li>
          ))}
        </ul>
      )}

      {/* Schedule trigger (hidden while a reveal is required or one is open). */}
      {showScheduleButton && !anonUnrevealed && (
        <Button
          variant="primary"
          size="sm"
          onClick={() => setScheduleOpen(true)}
        >
          <CalendarPlus aria-hidden weight="bold" className="size-4" />
          {t("scheduleCta")}
        </Button>
      )}
      {canSchedule && hasOpen && (
        <p className="text-xs text-[var(--text-muted)]">{t("openExistsHint")}</p>
      )}

      {/* Schedule modal */}
      <InterviewFormModal
        open={scheduleOpen}
        mode="create"
        applicationId={applicationId}
        onClose={() => setScheduleOpen(false)}
        onSuccess={() => {
          setScheduleOpen(false);
          invalidate();
          toast.show({ tone: "success", title: t("scheduledToast") });
        }}
        onRevealRequired={() => {
          setScheduleOpen(false);
          invalidate();
          toast.show({ tone: "warning", title: t("revealRequiredToast") });
        }}
        onInterviewExists={() => {
          setScheduleOpen(false);
          invalidate();
          toast.show({ tone: "warning", title: t("interviewExistsToast") });
        }}
      />

      {/* Reschedule / edit modal */}
      <InterviewFormModal
        open={!!editTarget}
        mode="edit"
        applicationId={applicationId}
        interview={editTarget ?? undefined}
        onClose={() => setEditTarget(null)}
        onSuccess={() => {
          setEditTarget(null);
          invalidate();
          toast.show({ tone: "success", title: t("rescheduledToast") });
        }}
        onRevealRequired={() => setEditTarget(null)}
        onInterviewExists={() => setEditTarget(null)}
      />

      {/* Assignees modal */}
      {assigneeTarget && (
        <AssigneesModal
          applicationId={applicationId}
          interview={assigneeTarget}
          onClose={() => setAssigneeTarget(null)}
          onSuccess={() => {
            setAssigneeTarget(null);
            invalidate();
            toast.show({ tone: "success", title: t("assigneesSavedToast") });
          }}
        />
      )}

      {/* Cancel confirm */}
      <ActionModal
        open={!!cancelTarget}
        title={t("cancelTitle")}
        description={t("cancelBody")}
        confirmLabel={t("cancelConfirm")}
        tone="danger"
        loadingFn={(version) =>
          applicationsApi.cancelInterview(
            applicationId,
            cancelTarget!.id,
            version,
          )
        }
        version={cancelTarget?.version}
        onClose={() => setCancelTarget(null)}
        onSuccess={() => {
          setCancelTarget(null);
          invalidate();
          toast.show({ tone: "success", title: t("cancelledToast") });
        }}
        onConflict={() => {
          setCancelTarget(null);
          invalidate();
          toast.show({ tone: "warning", title: t("conflictToast") });
        }}
        onError={(e) =>
          toast.show({ tone: "error", title: apiError(e) })
        }
      />

      {/* Complete (outcome) modal */}
      {completeTarget && (
        <CompleteModal
          applicationId={applicationId}
          interview={completeTarget}
          onClose={() => setCompleteTarget(null)}
          onSuccess={(outcome) => {
            setCompleteTarget(null);
            invalidate();
            toast.show({
              tone: "success",
              title:
                outcome === "no_show"
                  ? t("noShowToast")
                  : t("completedToast"),
            });
          }}
          onConflict={() => {
            setCompleteTarget(null);
            invalidate();
            toast.show({ tone: "warning", title: t("conflictToast") });
          }}
        />
      )}
    </section>
  );
}
